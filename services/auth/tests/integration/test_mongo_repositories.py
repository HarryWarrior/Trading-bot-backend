import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from auth_service.adapters.outbound.mongo_repositories import (
    MongoPasswordResetRepository,
    MongoSessionRepository,
    MongoUserRepository,
    MongoVerificationRepository,
)
from auth_service.domain.errors import EmailAlreadyRegistered
from auth_service.domain.user import Role, User
from trading_shared.mongo import create_mongo_client

pytestmark = pytest.mark.asyncio


MONGO_URL = "mongodb://localhost:27017"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def db():
    client = create_mongo_client(MONGO_URL)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    database = client[f"test_auth_{uuid.uuid4().hex}"]
    try:
        yield database
    finally:
        await client.drop_database(database.name)
        client.close()


def _user(user_id="u1", email="user@mail.com") -> User:
    return User(
        id=user_id,
        email=email,
        name="Ana",
        role=Role.USER,
        password_hash="h",
        email_verified=False,
        created_at=NOW,
    )


async def test_user_roundtrip_and_updates(db):
    repo = MongoUserRepository(db)
    await repo.create_indexes()
    await repo.add(_user())
    assert await repo.get_by_email("user@mail.com") == _user()
    assert await repo.get_by_id("u1") == _user()
    assert await repo.get_by_id("nope") is None
    await repo.mark_verified("u1")
    await repo.set_password_hash("u1", "h2")
    await repo.set_role("u1", Role.ADMIN)
    stored = await repo.get_by_id("u1")
    assert stored.email_verified is True
    assert stored.password_hash == "h2"
    assert stored.role == Role.ADMIN


async def test_unique_email_index_rejects_duplicates(db):
    repo = MongoUserRepository(db)
    await repo.create_indexes()
    await repo.add(_user("u1"))
    with pytest.raises(EmailAlreadyRegistered):
        await repo.add(_user("u2"))


async def test_session_consume_deletes_and_returns_user_id_once(db):
    repo = MongoSessionRepository(db)
    await repo.create_indexes()
    await repo.add("u1", "hash", NOW + timedelta(days=7))
    assert await repo.consume("hash", NOW) == "u1"
    assert await repo.consume("hash", NOW) is None


async def test_expired_session_is_not_consumable_including_boundary(db):
    repo = MongoSessionRepository(db)
    await repo.create_indexes()
    await repo.add("u1", "old", NOW - timedelta(seconds=1))
    await repo.add("u1", "edge", NOW)
    assert await repo.consume("old", NOW) is None
    assert await repo.consume("edge", NOW) is None


async def test_session_revoke_revoke_all_and_delete_expired(db):
    repo = MongoSessionRepository(db)
    await repo.create_indexes()
    future = NOW + timedelta(days=1)
    await repo.add("u1", "a", future)
    await repo.add("u1", "b", future)
    await repo.add("u2", "c", future)
    await repo.add("u2", "d", NOW - timedelta(days=1))
    await repo.revoke("a")
    assert await repo.consume("a", NOW) is None
    await repo.revoke_all("u1")
    assert await repo.consume("b", NOW) is None
    assert await repo.delete_expired(NOW) == 1
    assert await repo.consume("c", NOW) == "u2"


async def test_verification_replace_and_consume_once(db):
    repo = MongoVerificationRepository(db)
    await repo.create_indexes()
    await repo.replace_code("user@mail.com", "h1", NOW + timedelta(minutes=15))
    await repo.replace_code("user@mail.com", "h2", NOW + timedelta(minutes=15))
    assert await repo.consume("user@mail.com", "h1", NOW) is False
    assert await repo.consume("user@mail.com", "h2", NOW) is True
    assert await repo.consume("user@mail.com", "h2", NOW) is False


async def test_expired_verification_code_is_not_consumable(db):
    repo = MongoVerificationRepository(db)
    await repo.create_indexes()
    await repo.replace_code("user@mail.com", "h", NOW)
    assert await repo.consume("user@mail.com", "h", NOW) is False


async def test_password_reset_consume_once_and_expiry(db):
    repo = MongoPasswordResetRepository(db)
    await repo.create_indexes()
    await repo.add("u1", "t1", NOW + timedelta(hours=1))
    await repo.add("u1", "t2", NOW - timedelta(seconds=1))
    assert await repo.consume("t2", NOW) is None
    assert await repo.consume("t1", NOW) == "u1"
    assert await repo.consume("t1", NOW) is None


async def test_indexes_are_created(db):
    for repo, name in (
        (MongoUserRepository(db), "users"),
        (MongoVerificationRepository(db), "verification_codes"),
        (MongoSessionRepository(db), "sessions"),
        (MongoPasswordResetRepository(db), "password_resets"),
    ):
        await repo.create_indexes()
        info = await db[name].index_information()
        if name == "users":
            assert any(v.get("unique") and v["key"] == [("email", 1)] for v in info.values())
        else:
            assert any(
                v["key"] == [("expires_at", 1)] and v.get("expireAfterSeconds") == 0
                for v in info.values()
            )
