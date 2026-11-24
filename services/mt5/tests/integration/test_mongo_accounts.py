"""Mongo repository against a throwaway database (skipped when MongoDB is unreachable)."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from mt5_service.adapters.outbound.mongo_accounts import MongoLinkedAccountRepository
from mt5_service.adapters.outbound.system_clock import SystemClock
from mt5_service.adapters.outbound.uuid_ids import UuidIdGenerator
from mt5_service.domain.account import LinkedAccount, SyncResult
from mt5_service.domain.errors import AccountAlreadyLinked
from trading_shared.mongo import create_mongo_client

MONGO_URL = "mongodb://localhost:27017"
T0 = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)


def linked(account_id: str, user_id: str, ref: str = "123456@Demo-Server") -> LinkedAccount:
    login, server = ref.split("@")
    return LinkedAccount(
        id=account_id,
        user_id=user_id,
        account_ref=ref,
        login=int(login),
        server=server,
        name="Jane",
        currency="USD",
        trade_mode="demo",
        company="Broker",
        linked_at=T0,
    )


@pytest_asyncio.fixture
async def repo():
    client = create_mongo_client(MONGO_URL)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    db = client[f"test_mt5_{uuid.uuid4().hex}"]
    repository = MongoLinkedAccountRepository(db)
    await repository.create_indexes()
    try:
        yield repository
    finally:
        await client.drop_database(db.name)
        client.close()


def test_system_clock_and_ids():
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 0
    ids = UuidIdGenerator()
    assert ids.new_id() != ids.new_id()
    assert len(ids.new_id()) == 32


async def test_add_and_get_roundtrip_is_tz_aware(repo):
    await repo.add(linked("a1", "u1"))
    found = await repo.get("u1", "a1")
    assert found == linked("a1", "u1")
    assert found.linked_at.tzinfo is not None


async def test_account_ref_is_unique_across_users(repo):
    await repo.add(linked("a1", "u1"))
    with pytest.raises(AccountAlreadyLinked):
        await repo.add(linked("a2", "u2"))
    with pytest.raises(AccountAlreadyLinked):
        await repo.add(linked("a3", "u1"))


async def test_get_list_delete_are_scoped_by_user(repo):
    await repo.add(linked("a1", "u1", "1@S"))
    await repo.add(linked("a2", "u2", "2@S"))
    assert await repo.get("u2", "a1") is None
    assert [a.id for a in await repo.list("u1")] == ["a1"]
    assert await repo.delete("u2", "a1") is False
    assert await repo.get("u1", "a1") is not None
    assert await repo.delete("u1", "a1") is True
    assert await repo.get("u1", "a1") is None


async def test_find_by_ref_crosses_users(repo):
    await repo.add(linked("a1", "u1", "1@S"))
    assert (await repo.find_by_ref("1@S")).user_id == "u1"
    assert await repo.find_by_ref("nope@S") is None


async def test_mark_synced_stores_time_and_counts(repo):
    await repo.add(linked("a1", "u1"))
    result = SyncResult(
        created=3, updated=1, balance_events=2, open_positions=4, skipped_positions=5
    )
    await repo.mark_synced("a1", T0, result)
    found = await repo.get("u1", "a1")
    assert found.last_sync_at == T0
    assert found.last_sync_at.tzinfo is not None
    assert found.last_sync_result == result


async def test_list_is_ordered_by_link_time(repo):
    first = linked("a1", "u1", "1@S")
    second = replace(linked("a2", "u1", "2@S"), linked_at=datetime(2026, 3, 3, tzinfo=UTC))
    await repo.add(second)
    await repo.add(first)
    assert [a.id for a in await repo.list("u1")] == ["a1", "a2"]
