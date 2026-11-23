"""Shared test fakes and fixtures for every journal port."""

from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

# Keep the helper modules importable when this suite runs under another service pytest config
# (e.g. `pytest services/analytics/tests services/journal/tests`).
sys.path.insert(0, str(Path(__file__).parent / "unit"))

# starlette 0.27 imports the legacy `multipart` alias, which python-multipart >= 0.0.13 flags.
# Import it once here with the warning silenced so `-W error` does not trip on it later.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", PendingDeprecationWarning)
    import multipart  # noqa: F401

from journal_service.application.ports.parsing import ParsedReport, ParsedTrade
from journal_service.application.ports.repositories import AccountSummary, TradeFilters
from journal_service.application.use_cases.get_dataset import GetDataset
from journal_service.application.use_cases.get_trade import GetTrade
from journal_service.application.use_cases.import_report import ImportReport
from journal_service.application.use_cases.ingest_mt5_history import IngestMt5History
from journal_service.application.use_cases.list_accounts import ListAccounts
from journal_service.application.use_cases.list_imports import ListImports
from journal_service.application.use_cases.list_trades import ListTrades
from journal_service.domain.balance import BalanceEvent
from journal_service.domain.report_import import ReportImport
from journal_service.domain.trade import Side, Trade


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


class FakeParser:
    """Returns whatever report the test queued, regardless of the file content."""

    def __init__(self) -> None:
        self.report: ParsedReport | None = None
        self.calls = 0

    def parse(self, filename: str, content: bytes) -> ParsedReport:
        self.calls += 1
        assert self.report is not None
        return self.report


class FakeTradeRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], Trade] = {}

    @staticmethod
    def _key(user_id: str, trade: Trade) -> tuple[str, str, str]:
        natural = trade.position_id if trade.position_id is not None else trade.row_hash
        assert natural is not None
        return (user_id, trade.account_ref, natural)

    async def upsert_many(self, user_id: str, trades: list[Trade]) -> tuple[int, int]:
        created = updated = 0
        for trade in trades:
            key = self._key(user_id, trade)
            existing = self.rows.get(key)
            if existing is None:
                self.rows[key] = trade
                created += 1
            else:
                self.rows[key] = replace(trade, id=existing.id)
                updated += 1
        return created, updated

    def _mine(self, user_id: str) -> list[Trade]:
        return [t for t in self.rows.values() if t.user_id == user_id]

    async def list(
        self,
        user_id: str,
        filters: TradeFilters,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_dir: str,
    ) -> tuple[list[Trade], int]:
        items = [
            t
            for t in self._mine(user_id)
            if (filters.symbol is None or t.symbol == filters.symbol)
            and (filters.account_ref is None or t.account_ref == filters.account_ref)
            and (filters.outcome is None or t.outcome == filters.outcome)
        ]
        items.sort(key=lambda t: t.close_time, reverse=sort_dir == "desc")
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    async def get(self, user_id: str, trade_id: str) -> Trade | None:
        return next((t for t in self._mine(user_id) if t.id == trade_id), None)

    async def all_for(self, user_id: str, account_ref: str | None) -> list[Trade]:
        return [t for t in self._mine(user_id) if account_ref in (None, t.account_ref)]

    async def accounts(self, user_id: str) -> list[AccountSummary]:
        grouped: dict[str, list[Trade]] = {}
        for trade in self._mine(user_id):
            grouped.setdefault(trade.account_ref, []).append(trade)
        return [
            AccountSummary(
                account_ref=ref,
                trades=len(items),
                first_trade_at=min(t.close_time for t in items),
                last_trade_at=max(t.close_time for t in items),
            )
            for ref, items in grouped.items()
        ]


class FakeBalanceRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], BalanceEvent] = {}

    async def upsert_many(self, user_id: str, events: list[BalanceEvent]) -> int:
        for event in events:
            key = (user_id, event.account_ref, event.source_ref)
            existing = self.rows.get(key)
            self.rows[key] = replace(event, id=existing.id) if existing else event
        return len(events)

    async def all_for(self, user_id: str, account_ref: str | None) -> list[BalanceEvent]:
        return [
            e
            for e in self.rows.values()
            if e.user_id == user_id and account_ref in (None, e.account_ref)
        ]


class FakeImportRepository:
    def __init__(self) -> None:
        self.items: list[ReportImport] = []

    async def add(self, report_import: ReportImport) -> None:
        self.items.append(report_import)

    async def find_by_sha(self, user_id: str, sha256: str) -> ReportImport | None:
        return next((i for i in self.items if i.user_id == user_id and i.sha256 == sha256), None)

    async def list(self, user_id: str, page: int, page_size: int) -> tuple[list[ReportImport], int]:
        mine = [i for i in self.items if i.user_id == user_id]
        start = (page - 1) * page_size
        return mine[start : start + page_size], len(mine)


@dataclass
class World:
    clock: FixedClock
    ids: SequentialIds
    parser: FakeParser
    trades: FakeTradeRepository
    balances: FakeBalanceRepository
    imports: FakeImportRepository

    def import_report(self) -> ImportReport:
        return ImportReport(
            self.parser, self.trades, self.balances, self.imports, self.clock, self.ids
        )

    def ingest(self) -> IngestMt5History:
        return IngestMt5History(self.trades, self.balances, self.ids)

    def list_trades(self) -> ListTrades:
        return ListTrades(self.trades)

    def get_trade(self) -> GetTrade:
        return GetTrade(self.trades)

    def list_accounts(self) -> ListAccounts:
        return ListAccounts(self.trades)

    def list_imports(self) -> ListImports:
        return ListImports(self.imports)

    def dataset(self) -> GetDataset:
        return GetDataset(self.trades, self.balances)


@pytest.fixture
def journal() -> World:
    return World(
        clock=FixedClock(),
        ids=SequentialIds(),
        parser=FakeParser(),
        trades=FakeTradeRepository(),
        balances=FakeBalanceRepository(),
        imports=FakeImportRepository(),
    )


@pytest.fixture
def make_trade():
    def factory(**overrides) -> Trade:
        base = {
            "id": "t-1",
            "user_id": "u1",
            "account_ref": "123@Broker-Live",
            "position_id": "1",
            "row_hash": None,
            "source": "report",
            "import_id": None,
            "symbol": "EURUSD",
            "side": Side.BUY,
            "volume": Decimal("0.10"),
            "open_time": datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
            "close_time": datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
            "open_price": Decimal("1.1000"),
            "close_price": Decimal("1.1050"),
            "stop_loss": None,
            "take_profit": None,
            "commission": Decimal("0"),
            "swap": Decimal("0"),
            "profit": Decimal("50"),
            "comment": None,
        }
        base.update(overrides)
        return Trade(**base)

    return factory


@pytest.fixture
def parsed_trade():
    def factory(position_id: str | None, profit: str = "10", **overrides) -> ParsedTrade:
        base = {
            "position_id": position_id,
            "symbol": "EURUSD",
            "side": Side.BUY,
            "volume": Decimal("0.10"),
            "open_time": datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
            "close_time": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            "open_price": Decimal("1.1000"),
            "close_price": Decimal("1.1010"),
            "stop_loss": None,
            "take_profit": None,
            "commission": Decimal("0"),
            "swap": Decimal("0"),
            "profit": Decimal(profit),
            "comment": None,
        }
        base.update(overrides)
        return ParsedTrade(**base)

    return factory
