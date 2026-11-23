from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from journal_service.domain.balance import BalanceEvent
from journal_service.domain.report_import import ReportImport
from journal_service.domain.trade import Outcome, Trade


@dataclass(frozen=True)
class TradeFilters:
    symbol: str | None = None
    outcome: Outcome | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    profit_min: Decimal | None = None
    profit_max: Decimal | None = None
    account_ref: str | None = None
    q: str | None = None


@dataclass(frozen=True)
class AccountSummary:
    account_ref: str
    trades: int
    first_trade_at: datetime
    last_trade_at: datetime


class TradeRepository(Protocol):
    async def upsert_many(self, user_id: str, trades: list[Trade]) -> tuple[int, int]:
        """Upsert by natural key; return ``(created, updated)``. Existing ids are kept."""
        ...

    async def list(
        self,
        user_id: str,
        filters: TradeFilters,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_dir: str,
    ) -> tuple[list[Trade], int]: ...

    async def get(self, user_id: str, trade_id: str) -> Trade | None: ...

    async def all_for(self, user_id: str, account_ref: str | None) -> list[Trade]: ...

    async def accounts(self, user_id: str) -> list[AccountSummary]: ...


class BalanceRepository(Protocol):
    async def upsert_many(self, user_id: str, events: list[BalanceEvent]) -> int: ...

    async def all_for(self, user_id: str, account_ref: str | None) -> list[BalanceEvent]: ...


class ImportRepository(Protocol):
    async def add(self, report_import: ReportImport) -> None: ...

    async def find_by_sha(self, user_id: str, sha256: str) -> ReportImport | None: ...

    async def list(
        self, user_id: str, page: int, page_size: int
    ) -> tuple[list[ReportImport], int]: ...
