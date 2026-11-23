"""MongoDB (Motor) client factory and index helper. Adapters only."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo import IndexModel


def create_mongo_client(url: str) -> AsyncIOMotorClient:
    """Create an async Mongo client; connections are lazy, so this never blocks."""
    return AsyncIOMotorClient(url, tz_aware=True)


async def ensure_indexes(collection: AsyncIOMotorCollection, specs: list[IndexModel]) -> None:
    """Idempotently create the given indexes (no-op for an empty list)."""
    if specs:
        await collection.create_indexes(specs)
