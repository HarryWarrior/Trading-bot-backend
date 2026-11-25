"""Shared in-memory fakes for the mt5-bridge ports."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mt5_bridge_service.application.ports.journal import IngestDealsResult
from mt5_bridge_service.domain.account import BrokerAccount
from mt5_bridge_service.domain.deal import RawDeal
from mt5_bridge_service.domain.token import IngestToken


class FixedClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class SequentialIds:
    def __init__(self) -> None:
        self.counter = 0

    def new_id(self) -> str:
        self.counter += 1
        return f"id-{self.counter}"


class FakeTokenRepository:
    def __init__(self) -> None:
        self.rows: dict[str, IngestToken] = {}

    async def add(self, token: IngestToken) -> None:
        self.rows[token.id] = token

    async def get(self, user_id: str, token_id: str) -> IngestToken | None:
        token = self.rows.get(token_id)
        return token if token is not None and token.user_id == user_id else None

    async def list_for_user(self, user_id: str) -> list[IngestToken]:
        mine = [t for t in self.rows.values() if t.user_id == user_id]
        return sorted(mine, key=lambda t: (t.created_at, t.id), reverse=True)

    async def mark_revoked(self, user_id: str, token_id: str, at: datetime) -> None:
        token = await self.get(user_id, token_id)
        if token is not None and token.revoked_at is None:
            self.rows[token_id] = replace(token, revoked_at=at)

    async def find_active_by_hash(self, token_hash: str) -> IngestToken | None:
        return next((t for t in self.rows.values() if t.hash == token_hash and t.is_active), None)

    async def touch_last_used(self, user_id: str, token_id: str, at: datetime) -> None:
        token = await self.get(user_id, token_id)
        if token is not None:
            self.rows[token_id] = replace(token, last_used_at=at)


class FakeAccountRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], BrokerAccount] = {}

    async def upsert_heartbeat(self, account: BrokerAccount) -> BrokerAccount:
        key = (account.user_id, account.account_ref)
        existing = self.rows.get(key)
        stored = (
            account if existing is None else replace(account, last_deal_at=existing.last_deal_at)
        )
        self.rows[key] = stored
        return stored

    async def list_for_user(self, user_id: str) -> list[BrokerAccount]:
        mine = [a for a in self.rows.values() if a.user_id == user_id]
        return sorted(mine, key=lambda a: a.account_ref)

    async def touch_last_deal(self, user_id: str, account_ref: str, at: datetime) -> None:
        existing = self.rows.get((user_id, account_ref))
        if existing is None:
            return
        if existing.last_deal_at is None or at > existing.last_deal_at:
            self.rows[(user_id, account_ref)] = replace(existing, last_deal_at=at)


class FakeJournalGateway:
    """Records every forwarded batch; set ``error`` to make the next calls raise it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[RawDeal]]] = []
        self.error: Exception | None = None

    async def ingest_deals(
        self, user_id: str, account_ref: str, deals: list[RawDeal]
    ) -> IngestDealsResult:
        if self.error is not None:
            raise self.error
        self.calls.append((user_id, account_ref, list(deals)))
        return IngestDealsResult(received=len(deals), new=len(deals), trades_upserted=1)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def ids() -> SequentialIds:
    return SequentialIds()


@pytest.fixture
def tokens() -> FakeTokenRepository:
    return FakeTokenRepository()


@pytest.fixture
def accounts() -> FakeAccountRepository:
    return FakeAccountRepository()


@pytest.fixture
def journal() -> FakeJournalGateway:
    return FakeJournalGateway()
