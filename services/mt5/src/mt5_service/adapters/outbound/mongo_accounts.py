"""MongoDB repository for linked terminal accounts.

Datetimes are tz-aware UTC (the client is created with ``tz_aware=True``); ``_id`` is the domain
string id. ``account_ref`` is unique across ALL users: one terminal account, one owner.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel
from pymongo.errors import DuplicateKeyError

from mt5_service.domain.account import LinkedAccount, SyncResult
from mt5_service.domain.errors import AccountAlreadyLinked
from trading_shared.mongo import ensure_indexes


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _result_to_doc(result: SyncResult | None) -> dict[str, int] | None:
    if result is None:
        return None
    return {
        "created": result.created,
        "updated": result.updated,
        "balance_events": result.balance_events,
        "open_positions": result.open_positions,
        "skipped_positions": result.skipped_positions,
    }


def _to_doc(account: LinkedAccount) -> dict[str, Any]:
    return {
        "_id": account.id,
        "user_id": account.user_id,
        "account_ref": account.account_ref,
        "login": account.login,
        "server": account.server,
        "name": account.name,
        "currency": account.currency,
        "trade_mode": account.trade_mode,
        "company": account.company,
        "linked_at": account.linked_at,
        "last_sync_at": account.last_sync_at,
        "last_sync_result": _result_to_doc(account.last_sync_result),
    }


def _from_doc(doc: dict[str, Any]) -> LinkedAccount:
    raw = doc.get("last_sync_result")
    last_sync_at = doc.get("last_sync_at")
    return LinkedAccount(
        id=doc["_id"],
        user_id=doc["user_id"],
        account_ref=doc["account_ref"],
        login=doc["login"],
        server=doc["server"],
        name=doc["name"],
        currency=doc["currency"],
        trade_mode=doc["trade_mode"],
        company=doc["company"],
        linked_at=_utc(doc["linked_at"]),
        last_sync_at=None if last_sync_at is None else _utc(last_sync_at),
        last_sync_result=None if raw is None else SyncResult(**raw),
    )


class MongoLinkedAccountRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["linked_accounts"]

    async def create_indexes(self) -> None:
        await ensure_indexes(
            self._col,
            [
                IndexModel([("account_ref", ASCENDING)], unique=True, name="account_ref_unique"),
                IndexModel([("user_id", ASCENDING), ("linked_at", ASCENDING)], name="user_linked"),
            ],
        )

    async def add(self, account: LinkedAccount) -> None:
        try:
            await self._col.insert_one(_to_doc(account))
        except DuplicateKeyError as exc:
            raise AccountAlreadyLinked(account.account_ref) from exc

    async def get(self, user_id: str, account_id: str) -> LinkedAccount | None:
        doc = await self._col.find_one({"_id": account_id, "user_id": user_id})
        return None if doc is None else _from_doc(doc)

    async def find_by_ref(self, account_ref: str) -> LinkedAccount | None:
        doc = await self._col.find_one({"account_ref": account_ref})
        return None if doc is None else _from_doc(doc)

    async def list(self, user_id: str) -> list[LinkedAccount]:
        cursor = self._col.find({"user_id": user_id}).sort("linked_at", ASCENDING)
        return [_from_doc(doc) async for doc in cursor]

    async def delete(self, user_id: str, account_id: str) -> bool:
        result = await self._col.delete_one({"_id": account_id, "user_id": user_id})
        return result.deleted_count == 1

    async def mark_synced(self, account_id: str, at: datetime, result: SyncResult) -> None:
        await self._col.update_one(
            {"_id": account_id},
            {"$set": {"last_sync_at": at, "last_sync_result": _result_to_doc(result)}},
        )
