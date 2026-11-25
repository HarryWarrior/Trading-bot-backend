import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pymongo.errors
import pytest
import pytest_asyncio

from mt5_bridge_service.adapters.outbound.mongo_accounts import MongoAccountRepository
from mt5_bridge_service.adapters.outbound.mongo_tokens import MongoTokenRepository
from mt5_bridge_service.adapters.outbound.system_clock import SystemClock
from mt5_bridge_service.adapters.outbound.uuid_ids import UuidIdGenerator
from mt5_bridge_service.domain.account import BrokerAccount, Heartbeat
from mt5_bridge_service.domain.token import IngestToken, hash_token
from trading_shared.mongo import create_mongo_client

MONGO_URL = "mongodb://localhost:27017"
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def db():
    client = create_mongo_client(MONGO_URL)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    database = client[f"test_mt5_bridge_{uuid.uuid4().hex}"]
    try:
        yield database
    finally:
        await client.drop_database(database.name)
        client.close()


@pytest_asyncio.fixture
async def tokens(db):
    repo = MongoTokenRepository(db)
    await repo.create_indexes()
    return repo


@pytest_asyncio.fixture
async def accounts(db):
    repo = MongoAccountRepository(db)
    await repo.create_indexes()
    return repo


def _token(token_id: str = "t1", user_id: str = "u1", plaintext: str = "secret-1") -> IngestToken:
    return IngestToken(
        id=token_id,
        user_id=user_id,
        name="ea",
        hash=hash_token(plaintext),
        created_at=T0,
        last_used_at=None,
        revoked_at=None,
    )


def test_system_clock_and_ids():
    assert SystemClock().now().tzinfo is not None
    ids = UuidIdGenerator()
    assert ids.new_id() != ids.new_id()


async def test_token_roundtrip_and_hash_lookup(tokens, db):
    token = _token()
    await tokens.add(token)

    assert await tokens.get("u1", "t1") == token
    assert await tokens.get("u2", "t1") is None
    assert await tokens.find_active_by_hash(hash_token("secret-1")) == token
    assert await tokens.find_active_by_hash(hash_token("other")) is None
    stored = await db["ingest_tokens"].find_one({"_id": "t1"})
    assert "secret-1" not in str(stored)


async def test_token_hash_is_unique(tokens):
    await tokens.add(_token("t1"))
    with pytest.raises(pymongo.errors.DuplicateKeyError):
        await tokens.add(_token("t2"))


async def test_revoked_token_not_found_active(tokens):
    await tokens.add(_token())

    await tokens.mark_revoked("u2", "t1", T0)  # another user's revoke is a no-op
    assert await tokens.find_active_by_hash(hash_token("secret-1")) is not None

    await tokens.mark_revoked("u1", "t1", T0)
    await tokens.mark_revoked("u1", "t1", T0 + timedelta(hours=1))

    assert await tokens.find_active_by_hash(hash_token("secret-1")) is None
    assert (await tokens.get("u1", "t1")).revoked_at == T0


async def test_list_tokens_only_own_user_newest_first(tokens):
    await tokens.add(_token("old", plaintext="a"))
    await tokens.add(replace(_token("new", plaintext="b"), created_at=T0 + timedelta(minutes=1)))
    await tokens.add(_token("other", user_id="u2", plaintext="c"))

    assert [t.id for t in await tokens.list_for_user("u1")] == ["new", "old"]


async def test_touch_last_used_only_for_owner(tokens):
    await tokens.add(_token())
    await tokens.touch_last_used("u2", "t1", T0)
    assert (await tokens.get("u1", "t1")).last_used_at is None

    await tokens.touch_last_used("u1", "t1", T0 + timedelta(seconds=5))
    assert (await tokens.get("u1", "t1")).last_used_at == T0 + timedelta(seconds=5)


def _account(user_id: str = "u1", login: int = 123, balance: str = "1000.50", at=T0):
    hb = Heartbeat(
        login=login,
        server="Broker-Demo",
        balance=Decimal(balance),
        equity=Decimal("999.25"),
        terminal_build=4410,
    )
    return BrokerAccount.from_heartbeat(user_id, hb, at)


async def test_heartbeat_upserts_account_by_account_ref(accounts, db):
    first = await accounts.upsert_heartbeat(_account())
    await db["accounts"].update_one(
        {"account_ref": "123@Broker-Demo"}, {"$set": {"last_deal_at": T0}}
    )

    later = T0 + timedelta(minutes=1)
    second = await accounts.upsert_heartbeat(_account(balance="1100", at=later))

    assert first == _account()
    assert await db["accounts"].count_documents({}) == 1
    assert second.balance == Decimal("1100")
    assert second.equity == Decimal("999.25")
    assert second.last_heartbeat == later
    assert second.last_deal_at == T0
    assert second.terminal_build == 4410


async def test_list_accounts_only_returns_own_user(accounts):
    await accounts.upsert_heartbeat(_account("u1", 123))
    await accounts.upsert_heartbeat(_account("u2", 123))
    await accounts.upsert_heartbeat(_account("u1", 456))

    mine = await accounts.list_for_user("u1")

    assert [a.account_ref for a in mine] == ["123@Broker-Demo", "456@Broker-Demo"]
    assert {a.user_id for a in mine} == {"u1"}


async def test_account_key_is_unique_per_user(accounts, db):
    await accounts.upsert_heartbeat(_account())
    with pytest.raises(pymongo.errors.DuplicateKeyError):
        await db["accounts"].insert_one({"user_id": "u1", "account_ref": "123@Broker-Demo"})
