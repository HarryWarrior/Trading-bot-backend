"""MongoDB broker account store (collection ``accounts``), keyed by ``(user_id, account_ref)``.

Balance and equity are stored as ``Decimal128`` and converted back exactly.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from bson.decimal128 import Decimal128
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel, ReturnDocument

from mt5_bridge_service.domain.account import BrokerAccount
from trading_shared.mongo import ensure_indexes


class MongoAccountRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["accounts"]

    async def create_indexes(self) -> None:
        await ensure_indexes(
            self._col,
            [
                IndexModel(
                    [("user_id", ASCENDING), ("account_ref", ASCENDING)],
                    unique=True,
                    name="user_account_unique",
                ),
            ],
        )

    async def upsert_heartbeat(self, account: BrokerAccount) -> BrokerAccount:
        now: datetime | None = account.last_heartbeat
        doc = await self._col.find_one_and_update(
            {"user_id": account.user_id, "account_ref": account.account_ref},
            {
                "$set": {
                    "login": account.login,
                    "server": account.server,
                    "balance": Decimal128(account.balance),
                    "equity": Decimal128(account.equity),
                    "terminal_build": account.terminal_build,
                    "last_heartbeat": account.last_heartbeat,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now, "last_deal_at": None},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self._to_domain(doc)

    async def list_for_user(self, user_id: str) -> list[BrokerAccount]:
        cursor = self._col.find({"user_id": user_id}).sort("account_ref", ASCENDING)
        return [self._to_domain(doc) async for doc in cursor]

    async def touch_last_deal(self, user_id: str, account_ref: str, at: datetime) -> None:
        # $max: a backfill of old deals never moves last_deal_at backwards; BSON null < date.
        await self._col.update_one(
            {"user_id": user_id, "account_ref": account_ref}, {"$max": {"last_deal_at": at}}
        )

    @staticmethod
    def _to_domain(doc: dict[str, Any]) -> BrokerAccount:
        return BrokerAccount(
            user_id=doc["user_id"],
            account_ref=doc["account_ref"],
            login=doc["login"],
            server=doc["server"],
            balance=_dec(doc["balance"]),
            equity=_dec(doc["equity"]),
            last_heartbeat=doc.get("last_heartbeat"),
            last_deal_at=doc.get("last_deal_at"),
            terminal_build=doc.get("terminal_build"),
        )


def _dec(value: Decimal128) -> Decimal:
    return value.to_decimal()
