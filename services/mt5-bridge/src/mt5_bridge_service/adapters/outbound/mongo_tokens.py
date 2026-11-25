"""MongoDB ingest token store (collection ``ingest_tokens``; ``_id`` is the domain id).

Only the SHA-256 hash is stored, under a unique index. Datetimes are tz-aware UTC (the client is
created with ``tz_aware=True``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

from mt5_bridge_service.domain.token import IngestToken
from trading_shared.mongo import ensure_indexes


class MongoTokenRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["ingest_tokens"]

    async def create_indexes(self) -> None:
        await ensure_indexes(
            self._col,
            [
                IndexModel([("hash", ASCENDING)], unique=True, name="hash_unique"),
                IndexModel(
                    [("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"
                ),
            ],
        )

    async def add(self, token: IngestToken) -> None:
        await self._col.insert_one(self._to_doc(token))

    async def get(self, user_id: str, token_id: str) -> IngestToken | None:
        doc = await self._col.find_one({"_id": token_id, "user_id": user_id})
        return None if doc is None else self._to_domain(doc)

    async def list_for_user(self, user_id: str) -> list[IngestToken]:
        cursor = self._col.find({"user_id": user_id}).sort(
            [("created_at", DESCENDING), ("_id", DESCENDING)]
        )
        return [self._to_domain(doc) async for doc in cursor]

    async def mark_revoked(self, user_id: str, token_id: str, at: datetime) -> None:
        await self._col.update_one(
            {"_id": token_id, "user_id": user_id, "revoked_at": None},
            {"$set": {"revoked_at": at, "updated_at": at}},
        )

    async def find_active_by_hash(self, token_hash: str) -> IngestToken | None:
        # The one query without user_id: the hash is what identifies the owner.
        doc = await self._col.find_one({"hash": token_hash, "revoked_at": None})
        return None if doc is None else self._to_domain(doc)

    async def touch_last_used(self, user_id: str, token_id: str, at: datetime) -> None:
        await self._col.update_one(
            {"_id": token_id, "user_id": user_id}, {"$set": {"last_used_at": at}}
        )

    @staticmethod
    def _to_doc(token: IngestToken) -> dict[str, Any]:
        return {
            "_id": token.id,
            "user_id": token.user_id,
            "name": token.name,
            "hash": token.hash,
            "scope": token.scope,
            "created_at": token.created_at,
            "updated_at": token.created_at,
            "last_used_at": token.last_used_at,
            "revoked_at": token.revoked_at,
        }

    @staticmethod
    def _to_domain(doc: dict[str, Any]) -> IngestToken:
        return IngestToken(
            id=doc["_id"],
            user_id=doc["user_id"],
            name=doc["name"],
            hash=doc["hash"],
            created_at=doc["created_at"],
            last_used_at=doc.get("last_used_at"),
            revoked_at=doc.get("revoked_at"),
            scope=doc["scope"],
        )
