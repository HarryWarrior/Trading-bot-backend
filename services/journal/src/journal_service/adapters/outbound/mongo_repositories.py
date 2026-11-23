"""MongoDB repositories for the journal.

Conventions: decimals are stored as ``Decimal128`` and converted back exactly; datetimes are
tz-aware UTC (the client is created with ``tz_aware=True``); ``_id`` is the domain string id.
Trades carry a computed ``net`` (profit + commission + swap) so they can be filtered and sorted.
Natural keys are enforced by partial unique indexes; an absent key is a *missing* field, never null.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from bson.decimal128 import Decimal128
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel, UpdateOne
from pymongo.errors import DuplicateKeyError

from journal_service.application.ports.repositories import AccountSummary, TradeFilters
from journal_service.domain.balance import BalanceEvent
from journal_service.domain.errors import DuplicateImport
from journal_service.domain.report_import import ReportImport, SkippedRow
from journal_service.domain.trade import Outcome, Side, Trade
from trading_shared.mongo import ensure_indexes

_SORT_FIELDS = {
    "close_time": "close_time",
    "open_time": "open_time",
    "profit": "net",
    "symbol": "symbol",
}


def _d128(value: Decimal) -> Decimal128:
    return Decimal128(value)


def _opt_d128(value: Decimal | None) -> Decimal128 | None:
    return None if value is None else Decimal128(value)


def _dec(value: Decimal128) -> Decimal:
    return value.to_decimal()


def _opt_dec(value: Decimal128 | None) -> Decimal | None:
    return None if value is None else value.to_decimal()


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoTradeRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["trades"]

    async def create_indexes(self) -> None:
        await ensure_indexes(
            self._col,
            [
                IndexModel(
                    [
                        ("user_id", ASCENDING),
                        ("account_ref", ASCENDING),
                        ("position_id", ASCENDING),
                    ],
                    unique=True,
                    partialFilterExpression={"position_id": {"$type": "string"}},
                    name="natural_position_unique",
                ),
                IndexModel(
                    [("user_id", ASCENDING), ("account_ref", ASCENDING), ("row_hash", ASCENDING)],
                    unique=True,
                    partialFilterExpression={"row_hash": {"$type": "string"}},
                    name="natural_row_hash_unique",
                ),
                IndexModel([("user_id", ASCENDING), ("close_time", DESCENDING)], name="user_close"),
            ],
        )

    async def upsert_many(self, user_id: str, trades: list[Trade]) -> tuple[int, int]:
        if any(t.user_id != user_id for t in trades):
            raise ValueError("every trade must belong to the given user_id")
        if any(t.position_id is None and t.row_hash is None for t in trades):
            raise ValueError("every trade needs a position_id or row_hash")
        if not trades:
            return 0, 0
        now = datetime.now(UTC)
        ops = []
        for trade in trades:
            doc = self._to_doc(trade)
            natural = (
                {"position_id": trade.position_id}
                if trade.position_id is not None
                else {"row_hash": trade.row_hash}
            )
            key = {"user_id": user_id, "account_ref": trade.account_ref, **natural}
            insert_only = {"_id": doc.pop("_id"), "created_at": now}
            ops.append(UpdateOne(key, {"$set": doc, "$setOnInsert": insert_only}, upsert=True))
        result = await self._col.bulk_write(ops, ordered=True)
        return result.upserted_count, result.matched_count

    async def list(
        self,
        user_id: str,
        filters: TradeFilters,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_dir: str,
    ) -> tuple[list[Trade], int]:
        query = self._query(user_id, filters)
        field = _SORT_FIELDS.get(sort_by or "close_time", "close_time")
        direction = ASCENDING if sort_dir == "asc" else DESCENDING
        cursor = (
            self._col.find(query)
            .sort([(field, direction), ("_id", ASCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        items = [self._to_trade(doc) async for doc in cursor]
        total = await self._col.count_documents(query)
        return items, total

    async def get(self, user_id: str, trade_id: str) -> Trade | None:
        doc = await self._col.find_one({"_id": trade_id, "user_id": user_id})
        return None if doc is None else self._to_trade(doc)

    async def all_for(self, user_id: str, account_ref: str | None) -> list[Trade]:
        query: dict[str, Any] = {"user_id": user_id}
        if account_ref is not None:
            query["account_ref"] = account_ref
        cursor = self._col.find(query).sort([("close_time", ASCENDING), ("_id", ASCENDING)])
        return [self._to_trade(doc) async for doc in cursor]

    async def accounts(self, user_id: str) -> list[AccountSummary]:
        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$group": {
                    "_id": "$account_ref",
                    "trades": {"$sum": 1},
                    "first": {"$min": "$close_time"},
                    "last": {"$max": "$close_time"},
                }
            },
            {"$sort": {"_id": 1}},
        ]
        return [
            AccountSummary(
                account_ref=row["_id"],
                trades=row["trades"],
                first_trade_at=_utc(row["first"]),
                last_trade_at=_utc(row["last"]),
            )
            async for row in self._col.aggregate(pipeline)
        ]

    @staticmethod
    def _query(user_id: str, filters: TradeFilters) -> dict[str, Any]:
        """Build the filter. ``date_from`` is inclusive, ``date_to`` exclusive (on close_time)."""
        conds: list[dict[str, Any]] = [{"user_id": user_id}]
        if filters.symbol is not None:
            conds.append({"symbol": {"$regex": f"^{re.escape(filters.symbol)}$", "$options": "i"}})
        if filters.account_ref is not None:
            conds.append({"account_ref": filters.account_ref})
        if filters.outcome is not None:
            zero = _d128(Decimal(0))
            op = {Outcome.WIN: {"$gt": zero}, Outcome.LOSS: {"$lt": zero}}.get(
                filters.outcome, zero
            )
            conds.append({"net": op})
        close: dict[str, Any] = {}
        if filters.date_from is not None:
            close["$gte"] = filters.date_from
        if filters.date_to is not None:
            close["$lt"] = filters.date_to
        if close:
            conds.append({"close_time": close})
        net: dict[str, Any] = {}
        if filters.profit_min is not None:
            net["$gte"] = _d128(filters.profit_min)
        if filters.profit_max is not None:
            net["$lte"] = _d128(filters.profit_max)
        if net:
            conds.append({"net": net})
        if filters.q:
            rx = {"$regex": re.escape(filters.q), "$options": "i"}
            conds.append({"$or": [{"symbol": rx}, {"comment": rx}]})
        return conds[0] if len(conds) == 1 else {"$and": conds}

    @staticmethod
    def _to_doc(trade: Trade) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "_id": trade.id,
            "user_id": trade.user_id,
            "account_ref": trade.account_ref,
            "source": trade.source,
            "import_id": trade.import_id,
            "symbol": trade.symbol,
            "side": trade.side.value,
            "volume": _d128(trade.volume),
            "open_time": trade.open_time.astimezone(UTC),
            "close_time": trade.close_time.astimezone(UTC),
            "open_price": _d128(trade.open_price),
            "close_price": _d128(trade.close_price),
            "stop_loss": _opt_d128(trade.stop_loss),
            "take_profit": _opt_d128(trade.take_profit),
            "commission": _d128(trade.commission),
            "swap": _d128(trade.swap),
            "profit": _d128(trade.profit),
            "net": _d128(trade.net),
            "comment": trade.comment,
        }
        if trade.position_id is not None:
            doc["position_id"] = trade.position_id
        if trade.row_hash is not None:
            doc["row_hash"] = trade.row_hash
        return doc

    @staticmethod
    def _to_trade(doc: dict[str, Any]) -> Trade:
        return Trade(
            id=doc["_id"],
            user_id=doc["user_id"],
            account_ref=doc["account_ref"],
            position_id=doc.get("position_id"),
            row_hash=doc.get("row_hash"),
            source=doc["source"],
            import_id=doc.get("import_id"),
            symbol=doc["symbol"],
            side=Side(doc["side"]),
            volume=_dec(doc["volume"]),
            open_time=_utc(doc["open_time"]),
            close_time=_utc(doc["close_time"]),
            open_price=_dec(doc["open_price"]),
            close_price=_dec(doc["close_price"]),
            stop_loss=_opt_dec(doc.get("stop_loss")),
            take_profit=_opt_dec(doc.get("take_profit")),
            commission=_dec(doc["commission"]),
            swap=_dec(doc["swap"]),
            profit=_dec(doc["profit"]),
            comment=doc.get("comment"),
        )


class MongoBalanceRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["balance_events"]

    async def create_indexes(self) -> None:
        await ensure_indexes(
            self._col,
            [
                IndexModel(
                    [
                        ("user_id", ASCENDING),
                        ("account_ref", ASCENDING),
                        ("source_ref", ASCENDING),
                    ],
                    unique=True,
                    name="natural_source_ref_unique",
                ),
                IndexModel([("user_id", ASCENDING), ("time", ASCENDING)], name="user_time"),
            ],
        )

    async def upsert_many(self, user_id: str, events: list[BalanceEvent]) -> int:
        if any(e.user_id != user_id for e in events):
            raise ValueError("every balance event must belong to the given user_id")
        if not events:
            return 0
        now = datetime.now(UTC)
        ops = []
        for event in events:
            key = {
                "user_id": user_id,
                "account_ref": event.account_ref,
                "source_ref": event.source_ref,
            }
            doc = {
                "kind": event.kind,
                "amount": _d128(event.amount),
                "time": event.time.astimezone(UTC),
                "comment": event.comment,
            }
            ops.append(
                UpdateOne(
                    key,
                    {"$set": doc, "$setOnInsert": {"_id": event.id, "created_at": now}},
                    upsert=True,
                )
            )
        await self._col.bulk_write(ops, ordered=True)
        return len(events)

    async def all_for(self, user_id: str, account_ref: str | None) -> list[BalanceEvent]:
        query: dict[str, Any] = {"user_id": user_id}
        if account_ref is not None:
            query["account_ref"] = account_ref
        cursor = self._col.find(query).sort([("time", ASCENDING), ("_id", ASCENDING)])
        return [
            BalanceEvent(
                id=doc["_id"],
                user_id=doc["user_id"],
                account_ref=doc["account_ref"],
                kind=doc["kind"],
                amount=_dec(doc["amount"]),
                time=_utc(doc["time"]),
                source_ref=doc["source_ref"],
                comment=doc.get("comment"),
            )
            async for doc in cursor
        ]


class MongoImportRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["imports"]

    async def create_indexes(self) -> None:
        await ensure_indexes(
            self._col,
            [
                IndexModel(
                    [("user_id", ASCENDING), ("sha256", ASCENDING)],
                    unique=True,
                    name="user_sha256_unique",
                ),
                IndexModel(
                    [("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"
                ),
            ],
        )

    async def add(self, report_import: ReportImport) -> None:
        doc = {
            "_id": report_import.id,
            "user_id": report_import.user_id,
            "filename": report_import.filename,
            "sha256": report_import.sha256,
            "account_ref": report_import.account_ref,
            "trades_created": report_import.trades_created,
            "trades_updated": report_import.trades_updated,
            "balance_events": report_import.balance_events,
            "created_at": report_import.created_at.astimezone(UTC),
            "skipped_rows": [
                {"row": s.row, "reason": s.reason} for s in report_import.skipped_rows
            ],
        }
        try:
            await self._col.insert_one(doc)
        except DuplicateKeyError:
            existing = await self.find_by_sha(report_import.user_id, report_import.sha256)
            if existing is None:
                raise
            raise DuplicateImport(import_id=existing.id) from None

    async def find_by_sha(self, user_id: str, sha256: str) -> ReportImport | None:
        doc = await self._col.find_one({"user_id": user_id, "sha256": sha256})
        return None if doc is None else self._to_import(doc)

    async def list(self, user_id: str, page: int, page_size: int) -> tuple[list[ReportImport], int]:
        cursor = (
            self._col.find({"user_id": user_id})
            .sort([("created_at", DESCENDING), ("_id", ASCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        items = [self._to_import(doc) async for doc in cursor]
        return items, await self._col.count_documents({"user_id": user_id})

    @staticmethod
    def _to_import(doc: dict[str, Any]) -> ReportImport:
        return ReportImport(
            id=doc["_id"],
            user_id=doc["user_id"],
            filename=doc["filename"],
            sha256=doc["sha256"],
            account_ref=doc["account_ref"],
            trades_created=doc["trades_created"],
            trades_updated=doc["trades_updated"],
            balance_events=doc["balance_events"],
            created_at=_utc(doc["created_at"]),
            skipped_rows=[
                SkippedRow(row=s["row"], reason=s["reason"]) for s in doc["skipped_rows"]
            ],
        )
