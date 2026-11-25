"""Test doubles and builders. The fake terminal exists ONLY in tests; production never simulates."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from mt5_service.application.ports.journal import IngestResult
from mt5_service.domain.account import LinkedAccount, SyncResult, TerminalAccount
from mt5_service.domain.deals import Candle, Deal, DealEntry, DealType
from mt5_service.domain.errors import JournalUnavailable, SymbolNotFound, TerminalNotAvailable
from mt5_service.domain.trades import BalanceEventOut, TradeOut

D = Decimal


def terminal_account(
    login: int = 123456, server: str = "Demo-Server", **overrides
) -> TerminalAccount:
    values = dict(
        login=login,
        server=server,
        name="Jane Trader",
        currency="USD",
        balance=D("10000.00"),
        equity=D("10050.25"),
        trade_mode="demo",
        company="Demo Broker Ltd",
    )
    values.update(overrides)
    return TerminalAccount(**values)


def deal(
    ticket: int,
    position_id: int,
    time: str,
    type: DealType,
    entry: DealEntry,
    *,
    volume: str = "0",
    price: str = "0",
    profit: str = "0",
    commission: str = "0",
    swap: str = "0",
    fee: str = "0",
    symbol: str = "EURUSD",
    comment: str = "",
) -> Deal:
    return Deal(
        ticket=ticket,
        position_id=position_id,
        time_server=datetime.fromisoformat(time),
        type=type,
        entry=entry,
        symbol=symbol,
        volume=D(volume),
        price=D(price),
        commission=D(commission),
        swap=D(swap),
        fee=D(fee),
        profit=D(profit),
        comment=comment,
    )


def closed_position_deals(position_id: int = 7, first_ticket: int = 1) -> list[Deal]:
    return [
        deal(first_ticket, position_id, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN,
             volume="1.0", price="1.1000", commission="-2"),
        deal(first_ticket + 1, position_id, "2026-03-02T11:00:00", DealType.SELL, DealEntry.OUT,
             volume="1.0", price="1.1050", commission="-2", profit="50"),
    ]  # fmt: skip


def candle(time: str, close: str = "1.1000") -> Candle:
    return Candle(datetime.fromisoformat(time), D("1.0"), D("1.2"), D("0.9"), D(close), 10)


class FixedClock:
    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now


class SequentialIds:
    def __init__(self) -> None:
        self._n = 0

    def new_id(self) -> str:
        self._n += 1
        return f"acc-{self._n}"


class FakeTerminal:
    def __init__(self, account: TerminalAccount | None = None) -> None:
        self.account: TerminalAccount | None = account
        self.deals: list[Deal] = []
        self.candles: dict[str, list[Candle]] = {}
        # latest tick in broker SERVER time; 15:00:07 vs the default clock (12:00 UTC) -> +3h
        self.tick_time = datetime(2026, 3, 2, 15, 0, 7)
        self.history_calls = 0

    async def current_account(self) -> TerminalAccount:
        if self.account is None:
            raise TerminalNotAvailable("terminal is not running")
        return self.account

    async def history_deals(self) -> list[Deal]:
        self.history_calls += 1
        return list(self.deals)

    async def latest_tick_time(self, symbol: str | None) -> datetime:
        return self.tick_time

    async def rates(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        if self.account is None:
            raise TerminalNotAvailable("terminal is not running")
        if symbol not in self.candles:
            raise SymbolNotFound(symbol)
        return self.candles[symbol][:count]


class FakeJournalGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[TradeOut], list[BalanceEventOut]]] = []
        self.unavailable = False

    async def ingest(
        self,
        token: str,
        account_ref: str,
        trades: list[TradeOut],
        balance_events: list[BalanceEventOut],
    ) -> IngestResult:
        if self.unavailable:
            raise JournalUnavailable()
        self.calls.append((token, account_ref, list(trades), list(balance_events)))
        return IngestResult(created=len(trades), updated=0, balance_events=len(balance_events))


class InMemoryLinkedAccountRepository:
    def __init__(self) -> None:
        self.items: dict[str, LinkedAccount] = {}

    async def add(self, account: LinkedAccount) -> None:
        self.items[account.id] = account

    async def get(self, user_id: str, account_id: str) -> LinkedAccount | None:
        found = self.items.get(account_id)
        return found if found is not None and found.user_id == user_id else None

    async def find_by_ref(self, account_ref: str) -> LinkedAccount | None:
        return next((a for a in self.items.values() if a.account_ref == account_ref), None)

    async def list(self, user_id: str) -> list[LinkedAccount]:
        return [a for a in self.items.values() if a.user_id == user_id]

    async def delete(self, user_id: str, account_id: str) -> bool:
        if await self.get(user_id, account_id) is None:
            return False
        del self.items[account_id]
        return True

    async def mark_synced(self, account_id: str, at: datetime, result: SyncResult) -> None:
        self.items[account_id] = replace(
            self.items[account_id], last_sync_at=at, last_sync_result=result
        )
