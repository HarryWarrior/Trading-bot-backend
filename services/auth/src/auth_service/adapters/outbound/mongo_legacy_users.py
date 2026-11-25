"""Read-only adapter over the legacy app's ``users`` collection."""

from motor.motor_asyncio import AsyncIOMotorDatabase

from auth_service.application.ports.legacy_users import LegacyUser


class MongoLegacyUserSource:
    def __init__(self, db: AsyncIOMotorDatabase, collection: str = "users") -> None:
        self._col = db[collection]

    async def list_users(self) -> list[LegacyUser]:
        users: list[LegacyUser] = []
        async for doc in self._col.find({}).sort("created_at", 1):
            verified = doc.get("email_verified")
            users.append(
                LegacyUser(
                    id=str(doc["_id"]),
                    email=doc.get("email"),
                    password_hash=doc.get("password_hash"),
                    name=doc.get("name"),
                    role=doc.get("role"),
                    email_verified=verified if isinstance(verified, bool) else None,
                    created_at=doc.get("created_at"),
                )
            )
        return users
