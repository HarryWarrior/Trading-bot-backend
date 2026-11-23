"""MongoDB repositories. Datetimes are stored tz-aware UTC (client created with tz_aware=True).

Expiry boundary: a record is valid only while ``expires_at > now``.
"""

from dataclasses import asdict
from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel
from pymongo.errors import DuplicateKeyError

from auth_service.domain.errors import EmailAlreadyRegistered
from auth_service.domain.user import Role, User
from trading_shared.mongo import ensure_indexes


def _ttl_index() -> IndexModel:
    return IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="expires_at_ttl")


class MongoUserRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["users"]

    async def create_indexes(self) -> None:
        await ensure_indexes(
            self._col, [IndexModel([("email", ASCENDING)], unique=True, name="email_unique")]
        )

    async def add(self, user: User) -> None:
        doc = asdict(user)
        doc["_id"] = doc.pop("id")
        doc["role"] = user.role.value
        try:
            await self._col.insert_one(doc)
        except DuplicateKeyError as exc:
            raise EmailAlreadyRegistered("Email is already registered") from exc

    async def get_by_email(self, email: str) -> User | None:
        return self._to_user(await self._col.find_one({"email": email}))

    async def get_by_id(self, user_id: str) -> User | None:
        return self._to_user(await self._col.find_one({"_id": user_id}))

    async def mark_verified(self, user_id: str) -> None:
        await self._col.update_one({"_id": user_id}, {"$set": {"email_verified": True}})

    async def set_password_hash(self, user_id: str, password_hash: str) -> None:
        await self._col.update_one({"_id": user_id}, {"$set": {"password_hash": password_hash}})

    async def set_role(self, user_id: str, role: Role) -> None:
        await self._col.update_one({"_id": user_id}, {"$set": {"role": role.value}})

    @staticmethod
    def _to_user(doc: dict[str, Any] | None) -> User | None:
        if doc is None:
            return None
        return User(
            id=doc["_id"],
            email=doc["email"],
            name=doc["name"],
            role=Role(doc["role"]),
            password_hash=doc["password_hash"],
            email_verified=doc["email_verified"],
            created_at=doc["created_at"],
        )


class MongoVerificationRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["verification_codes"]

    async def create_indexes(self) -> None:
        await ensure_indexes(
            self._col,
            [IndexModel([("email", ASCENDING)], unique=True, name="email_unique"), _ttl_index()],
        )

    async def replace_code(self, email: str, code_hash: str, expires_at: datetime) -> None:
        await self._col.replace_one(
            {"email": email},
            {"email": email, "code_hash": code_hash, "expires_at": expires_at},
            upsert=True,
        )

    async def consume(self, email: str, code_hash: str, now: datetime) -> bool:
        deleted = await self._col.find_one_and_delete(
            {"email": email, "code_hash": code_hash, "expires_at": {"$gt": now}}
        )
        return deleted is not None


class MongoSessionRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["sessions"]

    async def create_indexes(self) -> None:
        await ensure_indexes(
            self._col,
            [
                IndexModel([("token_hash", ASCENDING)], unique=True, name="token_hash_unique"),
                IndexModel([("user_id", ASCENDING)], name="user_id"),
                _ttl_index(),
            ],
        )

    async def add(self, user_id: str, token_hash: str, expires_at: datetime) -> None:
        await self._col.insert_one(
            {"token_hash": token_hash, "user_id": user_id, "expires_at": expires_at}
        )

    async def consume(self, token_hash: str, now: datetime) -> str | None:
        doc = await self._col.find_one_and_delete(
            {"token_hash": token_hash, "expires_at": {"$gt": now}}
        )
        return None if doc is None else doc["user_id"]

    async def revoke(self, token_hash: str) -> None:
        await self._col.delete_one({"token_hash": token_hash})

    async def revoke_all(self, user_id: str) -> None:
        await self._col.delete_many({"user_id": user_id})

    async def delete_expired(self, now: datetime) -> int:
        result = await self._col.delete_many({"expires_at": {"$lte": now}})
        return result.deleted_count


class MongoPasswordResetRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["password_resets"]

    async def create_indexes(self) -> None:
        await ensure_indexes(
            self._col,
            [
                IndexModel([("token_hash", ASCENDING)], unique=True, name="token_hash_unique"),
                IndexModel([("user_id", ASCENDING)], name="user_id"),
                _ttl_index(),
            ],
        )

    async def add(self, user_id: str, token_hash: str, expires_at: datetime) -> None:
        await self._col.insert_one(
            {"token_hash": token_hash, "user_id": user_id, "expires_at": expires_at}
        )

    async def consume(self, token_hash: str, now: datetime) -> str | None:
        doc = await self._col.find_one_and_delete(
            {"token_hash": token_hash, "expires_at": {"$gt": now}}
        )
        return None if doc is None else doc["user_id"]

    async def revoke_all(self, user_id: str) -> None:
        await self._col.delete_many({"user_id": user_id})
