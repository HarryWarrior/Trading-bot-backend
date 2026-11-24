"""Mapping tests for the MetaTrader5 adapter using a fake ``MetaTrader5`` module object."""

import asyncio
import sys
import threading
from collections import namedtuple
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from mt5_service.adapters.outbound.mt5_terminal import MetaTrader5TerminalAdapter
from mt5_service.domain.deals import DealEntry, DealType
from mt5_service.domain.errors import InvalidTimeframe, SymbolNotFound, TerminalNotAvailable

AccountInfo = namedtuple(
    "AccountInfo", "login server name currency balance equity trade_mode company"
)
TradeDeal = namedtuple(
    "TradeDeal",
    "ticket position_id time time_msc type entry symbol volume price commission swap fee profit "
    "comment",
)
SymbolInfo = namedtuple("SymbolInfo", "name visible digits")
Tick = namedtuple("Tick", "time bid ask")

T0 = int((datetime(2026, 3, 2, 15, 0, 0) - datetime(1970, 1, 1)).total_seconds())


class FakeMt5:
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.threads: list[int] = []
        self.init_ok = True
        self.error = (1, "Success")
        self.account = AccountInfo(
            123456, "Demo-Server", "Jane Trader", "USD", 10000.1, 10050.25, 0, "Demo Broker"
        )
        self.deals = []
        self.symbols = [SymbolInfo("EURUSD", True, 5), SymbolInfo("XAUUSD", False, 2)]
        self.ticks: dict[str, Tick] = {}
        self.rates: dict[str, list[dict] | None] = {}
        self.select_ok = True

    def _rec(self, name: str, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))
        self.threads.append(threading.get_ident())

    def initialize(self, *args, **kwargs) -> bool:
        self._rec("initialize", *args, **kwargs)
        return self.init_ok

    def shutdown(self) -> None:
        self._rec("shutdown")

    def last_error(self):
        return self.error

    def account_info(self):
        self._rec("account_info")
        return self.account

    def history_deals_get(self, date_from, date_to):
        self._rec("history_deals_get", date_from, date_to)
        return self.deals

    def symbols_get(self):
        self._rec("symbols_get")
        return tuple(self.symbols)

    def symbol_select(self, name, enable):
        self._rec("symbol_select", name, enable)
        return self.select_ok

    def symbol_info(self, name):
        self._rec("symbol_info", name)
        return next((s for s in self.symbols if s.name == name), None)

    def symbol_info_tick(self, name):
        self._rec("symbol_info_tick", name)
        return self.ticks.get(name)

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        self._rec("copy_rates_from_pos", symbol, timeframe, start_pos, count)
        return self.rates.get(symbol)


def make_deal(ticket=1, time=T0, symbol="EURUSD", **kw) -> TradeDeal:
    values = dict(
        ticket=ticket, position_id=7, time=time, time_msc=time * 1000, type=0, entry=0,
        symbol=symbol, volume=0.1, price=1.1, commission=-0.7, swap=0.0, fee=0.0, profit=0.0,
        comment="c",
    )  # fmt: skip
    values.update(kw)
    return TradeDeal(**values)


@pytest.fixture
def mt5() -> FakeMt5:
    return FakeMt5()


@pytest.fixture
def adapter(mt5):
    return MetaTrader5TerminalAdapter(module=mt5)


async def test_not_installed_is_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "MetaTrader5", None)  # makes `import MetaTrader5` fail
    with pytest.raises(TerminalNotAvailable, match="MetaTrader5 package not installed"):
        await MetaTrader5TerminalAdapter().current_account()


async def test_initialize_false_is_unavailable_with_last_error(mt5, adapter):
    mt5.init_ok = False
    mt5.error = (-10005, "IPC timeout")
    with pytest.raises(TerminalNotAvailable, match=r"terminal not available: \(-10005, 'IPC"):
        await adapter.current_account()


async def test_not_logged_in_is_unavailable(mt5, adapter):
    mt5.account = None
    with pytest.raises(TerminalNotAvailable, match="terminal not logged in"):
        await adapter.current_account()


async def test_initialize_never_receives_credentials(mt5, adapter):
    await adapter.current_account()
    await adapter.current_account()
    inits = [c for c in mt5.calls if c[0] == "initialize"]
    assert len(inits) == 1  # connects once, reuses the session
    assert all(args == () and kwargs == {} for _, args, kwargs in inits)


async def test_failed_initialize_is_retried_next_call(mt5, adapter):
    mt5.init_ok = False
    with pytest.raises(TerminalNotAvailable):
        await adapter.current_account()
    mt5.init_ok = True
    assert (await adapter.current_account()).login == 123456
    assert len([c for c in mt5.calls if c[0] == "initialize"]) == 2


async def test_account_mapping_uses_decimal_via_str(adapter):
    account = await adapter.current_account()
    assert account.login == 123456 and account.server == "Demo-Server"
    assert account.account_ref == "123456@Demo-Server"
    assert (account.name, account.currency, account.company) == (
        "Jane Trader",
        "USD",
        "Demo Broker",
    )
    assert account.balance == Decimal("10000.1")  # not 10000.1000000000004...
    assert account.equity == Decimal("10050.25")
    assert account.trade_mode == "demo"


@pytest.mark.parametrize("mode,expected", [(0, "demo"), (1, "contest"), (2, "real")])
async def test_trade_mode_mapping(mt5, adapter, mode, expected):
    mt5.account = mt5.account._replace(trade_mode=mode)
    assert (await adapter.current_account()).trade_mode == expected


async def test_unknown_trade_mode_is_not_guessed(mt5, adapter):
    mt5.account = mt5.account._replace(trade_mode=9)
    with pytest.raises(TerminalNotAvailable, match="trade mode"):
        await adapter.current_account()


async def test_history_deals_mapping(mt5, adapter):
    mt5.deals = [
        make_deal(1, type=0, entry=0, volume=0.1, price=1.1),
        make_deal(2, type=1, entry=1, profit=12.34, commission=-0.7, swap=-0.1, fee=-0.02),
    ]
    deals = await adapter.history_deals()
    assert len(deals) == 2
    first = deals[0]
    assert first.time_server == datetime(2026, 3, 2, 15, 0, 0)  # naive SERVER time
    assert first.time_server.tzinfo is None
    assert (first.type, first.entry) == (DealType.BUY, DealEntry.IN)
    assert first.volume == Decimal("0.1") and first.price == Decimal("1.1")
    assert first.commission == Decimal("-0.7") and first.comment == "c"
    second = deals[1]
    assert (second.type, second.entry) == (DealType.SELL, DealEntry.OUT)
    assert second.profit == Decimal("12.34") and second.swap == Decimal("-0.1")
    assert second.fee == Decimal("-0.02") and second.position_id == 7 and second.ticket == 2


async def test_history_deals_range_is_whole_history_up_to_tomorrow(mt5, adapter):
    before = datetime.now()
    await adapter.history_deals()
    _, (date_from, date_to), _ = next(c for c in mt5.calls if c[0] == "history_deals_get")
    assert date_from == datetime(2000, 1, 1)
    assert before + timedelta(hours=23) < date_to < datetime.now() + timedelta(hours=25)


async def test_history_deals_none_with_ok_status_is_empty(mt5, adapter):
    mt5.deals = None  # MT5 returns None with RES_S_OK when there is nothing
    assert await adapter.history_deals() == []


async def test_history_deals_none_with_error_is_unavailable_then_reconnects(mt5, adapter):
    mt5.deals = None
    mt5.error = (-10004, "No IPC connection")
    with pytest.raises(TerminalNotAvailable, match="No IPC connection"):
        await adapter.history_deals()
    mt5.error = (1, "Success")
    mt5.deals = []
    await adapter.history_deals()
    assert len([c for c in mt5.calls if c[0] == "initialize"]) == 2
    assert any(c[0] == "shutdown" for c in mt5.calls)


async def test_rates_mapping_selects_symbol_and_uses_timeframe_constant(mt5, adapter):
    mt5.rates["EURUSD"] = [
        {"time": T0, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "tick_volume": 42},
        {"time": T0 + 3600, "open": 1.15, "high": 1.3, "low": 1.1, "close": 1.2, "tick_volume": 7},
    ]
    candles = await adapter.rates("EURUSD", "H1", 2)
    assert [c.time for c in candles] == [
        datetime(2026, 3, 2, 15, 0, 0),
        datetime(2026, 3, 2, 16, 0, 0),
    ]
    assert candles[0].open == Decimal("1.1") and candles[0].close == Decimal("1.15")
    assert candles[0].tick_volume == 42 and isinstance(candles[0].tick_volume, int)
    names = [c[0] for c in mt5.calls]
    assert names.index("symbol_select") < names.index("copy_rates_from_pos")
    assert ("symbol_select", ("EURUSD", True), {}) in mt5.calls
    assert ("copy_rates_from_pos", ("EURUSD", FakeMt5.TIMEFRAME_H1, 0, 2), {}) in mt5.calls


async def test_rates_unknown_symbol(adapter):
    with pytest.raises(SymbolNotFound):
        await adapter.rates("NOPE", "H1", 5)


async def test_rates_symbol_select_failure_is_symbol_not_found(mt5, adapter):
    mt5.select_ok = False
    with pytest.raises(SymbolNotFound):
        await adapter.rates("EURUSD", "H1", 5)


async def test_rates_unknown_timeframe(adapter):
    with pytest.raises(InvalidTimeframe):
        await adapter.rates("EURUSD", "W1", 5)


async def test_rates_none_is_unavailable(mt5, adapter):
    mt5.rates["EURUSD"] = None
    mt5.error = (-10004, "No IPC connection")
    with pytest.raises(TerminalNotAvailable, match="No IPC connection"):
        await adapter.rates("EURUSD", "M1", 5)


async def test_latest_tick_time_for_symbol(mt5, adapter):
    mt5.ticks["EURUSD"] = Tick(T0, 1.1, 1.1)
    assert await adapter.latest_tick_time("EURUSD") == datetime(2026, 3, 2, 15, 0, 0)


async def test_latest_tick_time_unknown_symbol(adapter):
    with pytest.raises(SymbolNotFound):
        await adapter.latest_tick_time("NOPE")


async def test_latest_tick_time_without_symbol_uses_freshest_visible_symbol(mt5, adapter):
    mt5.symbols = [SymbolInfo("A", True, 5), SymbolInfo("B", True, 5), SymbolInfo("C", False, 5)]
    mt5.ticks = {
        "A": Tick(T0, 1, 1),
        "B": Tick(T0 + 60, 1, 1),
        "C": Tick(T0 + 9999, 1, 1),  # not in Market Watch: ignored
    }
    assert await adapter.latest_tick_time(None) == datetime(2026, 3, 2, 15, 1, 0)
    assert ("symbol_info_tick", ("C",), {}) not in mt5.calls


async def test_latest_tick_time_without_symbol_includes_last_deal_symbol(mt5, adapter):
    mt5.symbols = [SymbolInfo("A", True, 5)]
    mt5.ticks = {"A": Tick(T0, 1, 1), "GBPUSD": Tick(T0 + 120, 1, 1)}
    mt5.deals = [
        make_deal(1, time=T0 - 500, symbol="A"),
        make_deal(2, time=T0 - 100, symbol="GBPUSD"),
        make_deal(3, time=T0 - 50, symbol="", type=2),  # balance deal: no symbol
    ]
    assert await adapter.latest_tick_time(None) == datetime(2026, 3, 2, 15, 2, 0)


async def test_latest_tick_time_without_any_tick_is_unavailable(mt5, adapter):
    mt5.ticks = {"EURUSD": Tick(0, 0, 0)}  # zero time = no data
    with pytest.raises(TerminalNotAvailable, match="no market data to derive server time"):
        await adapter.latest_tick_time(None)


async def test_every_call_runs_on_the_same_single_worker_thread(mt5, adapter):
    mt5.ticks["EURUSD"] = Tick(T0, 1, 1)
    mt5.rates["EURUSD"] = []
    await adapter.current_account()
    await adapter.history_deals()
    await adapter.latest_tick_time("EURUSD")
    await adapter.rates("EURUSD", "M5", 1)
    assert len(set(mt5.threads)) == 1
    assert mt5.threads[0] != threading.get_ident()


async def test_concurrent_calls_are_serialized(mt5, adapter):
    results = await asyncio.gather(*(adapter.current_account() for _ in range(5)))
    assert all(r.login == 123456 for r in results)
    assert len(set(mt5.threads)) == 1


async def test_unknown_deal_type_and_entry_are_kept_as_raw_ints(mt5, adapter):
    mt5.deals = [make_deal(1, type=99, entry=9)]
    deal = (await adapter.history_deals())[0]
    assert deal.type == 99 and deal.entry == 9
    assert not isinstance(deal.type, DealType) and not isinstance(deal.entry, DealEntry)


async def test_not_logged_in_resets_session_and_reconnects(mt5, adapter):
    mt5.account = None
    with pytest.raises(TerminalNotAvailable, match="terminal not logged in"):
        await adapter.current_account()
    assert any(c[0] == "shutdown" for c in mt5.calls)
    mt5.account = AccountInfo(1, "S", "N", "USD", 1.0, 1.0, 2, "C")
    assert (await adapter.current_account()).trade_mode == "real"
    assert len([c for c in mt5.calls if c[0] == "initialize"]) == 2


async def test_no_market_data_resets_session(mt5, adapter):
    with pytest.raises(TerminalNotAvailable, match="no market data"):
        await adapter.latest_tick_time(None)
    assert any(c[0] == "shutdown" for c in mt5.calls)
