"""BrokerTerminal adapter over the official ``MetaTrader5`` Python package.

The package talks to the MT5 terminal that is already running and logged in on this machine
(Windows only). The account is whatever the terminal reports and no credential ever passes through
this service: ``initialize`` only ever receives ``path`` (never login/password/server).

``initialize()`` would LAUNCH terminal64.exe when none is running (ADR 0004: attach to the OPEN
terminal only), so a ``TerminalProcessProbe`` is asked first: no terminal -> TerminalNotAvailable
without calling initialize; several -> MultipleTerminals; exactly one -> initialize(path=<its exe>).

The package is not thread safe, so every call runs on one dedicated worker thread under a lock and
is awaited through ``run_in_executor``. All epoch times MT5 returns are broker SERVER time and are
converted to naive datetimes (never through the local time zone).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, TypeVar

from mt5_service.adapters.outbound.psutil_probe import PsutilTerminalProbe
from mt5_service.application.ports.terminal_probe import TerminalProcessProbe
from mt5_service.domain.account import TerminalAccount, TradeMode
from mt5_service.domain.deals import Candle, Deal, DealEntry, DealType
from mt5_service.domain.errors import (
    InvalidTimeframe,
    MultipleTerminals,
    SymbolNotFound,
    TerminalNotAvailable,
)

T = TypeVar("T")

_EPOCH = datetime(1970, 1, 1)
_RES_OK = 1  # MT5 RES_S_OK
_TRADE_MODES: dict[int, TradeMode] = {0: "demo", 1: "contest", 2: "real"}
_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")


def _server_time(epoch_seconds: Any) -> datetime:
    return _EPOCH + timedelta(seconds=int(epoch_seconds))


def _enum(cls: type, value: Any) -> Any:
    """The enum member, or the raw int when the broker reports a value we do not know."""
    number = int(value)
    try:
        return cls(number)
    except ValueError:
        return number


def _dec(value: Any) -> Decimal:
    return Decimal(str(float(value)))


class MetaTrader5TerminalAdapter:
    def __init__(
        self,
        module: Any | None = None,
        executor: Executor | None = None,
        probe: TerminalProcessProbe | None = None,
    ) -> None:
        self._module = module
        self._probe = probe or PsutilTerminalProbe()
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="mt5-terminal"
        )
        self._owns_executor = executor is None
        self._lock = threading.Lock()
        self._initialized = False

    # ---- BrokerTerminal -------------------------------------------------------------------

    async def current_account(self) -> TerminalAccount:
        return await self._run(self._current_account)

    async def history_deals(self) -> list[Deal]:
        return await self._run(self._history_deals)

    async def latest_tick_time(self, symbol: str | None) -> datetime:
        return await self._run(lambda mt5: self._latest_tick_time(mt5, symbol))

    async def rates(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        return await self._run(lambda mt5: self._rates(mt5, symbol, timeframe, count))

    async def close(self) -> None:
        """Detaches from the terminal (does not close the terminal itself)."""
        if self._module is not None or self._initialized:
            await self._run(self._shutdown, connect=False)
        if self._owns_executor:
            self._executor.shutdown(wait=False)

    # ---- plumbing -------------------------------------------------------------------------

    async def _run(self, fn: Callable[[Any], T], *, connect: bool = True) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._locked, fn, connect)

    def _locked(self, fn: Callable[[Any], T], connect: bool) -> T:
        with self._lock:
            mt5 = self._load()
            if connect:
                self._connect(mt5)
            return fn(mt5)

    def _load(self) -> Any:
        if self._module is None:
            try:
                import MetaTrader5  # noqa: PLC0415 - lazy: package exists on Windows only
            except ImportError as exc:
                raise TerminalNotAvailable("MetaTrader5 package not installed") from exc
            self._module = MetaTrader5
        return self._module

    def _connect(self, mt5: Any) -> None:
        if self._initialized:
            return
        running = self._probe.running_terminals()
        if not running:  # initialize() would start terminal64.exe: never call it then
            raise TerminalNotAvailable("MT5 terminal is not running")
        if len(running) > 1:
            raise MultipleTerminals
        if not mt5.initialize(path=running[0]):  # no login/password/server
            raise TerminalNotAvailable(f"terminal not available: {mt5.last_error()}")
        self._initialized = True

    def _shutdown(self, mt5: Any) -> None:
        if self._initialized:
            mt5.shutdown()
        self._initialized = False

    def _fail(self, mt5: Any, what: str) -> TerminalNotAvailable:
        """Drops the session (so the next call reconnects) and builds the error."""
        error = mt5.last_error()
        self._shutdown(mt5)
        return TerminalNotAvailable(f"{what}: {error}")

    @staticmethod
    def _is_ok(mt5: Any) -> bool:
        error = mt5.last_error()
        return bool(error) and error[0] == _RES_OK

    # ---- operations (run on the worker thread) --------------------------------------------

    def _current_account(self, mt5: Any) -> TerminalAccount:
        info = mt5.account_info()
        if info is None:
            raise self._fail(mt5, "terminal not logged in")
        try:
            trade_mode = _TRADE_MODES[int(info.trade_mode)]
        except (KeyError, ValueError):
            raise TerminalNotAvailable(f"unknown account trade mode {info.trade_mode}") from None
        return TerminalAccount(
            login=int(info.login),
            server=str(info.server),
            name=str(info.name),
            currency=str(info.currency),
            balance=_dec(info.balance),
            equity=_dec(info.equity),
            trade_mode=trade_mode,
            company=str(info.company),
        )

    def _raw_deals(self, mt5: Any) -> list[Any]:
        # The package reads naive datetimes as LOCAL time. End = local now + 2 days: generous enough
        # to include every deal whatever the broker offset (up to UTC+14) and the local zone.
        raw = mt5.history_deals_get(datetime(2000, 1, 1), datetime.now() + timedelta(days=2))
        if raw is None:
            if not self._is_ok(mt5):
                raise self._fail(mt5, "cannot read deal history")
            return []
        return list(raw)

    def _history_deals(self, mt5: Any) -> list[Deal]:
        return [
            Deal(
                ticket=int(d.ticket),
                position_id=int(d.position_id),
                time_server=_server_time(d.time),
                type=_enum(DealType, d.type),
                entry=_enum(DealEntry, d.entry),
                symbol=str(d.symbol),
                volume=_dec(d.volume),
                price=_dec(d.price),
                commission=_dec(d.commission),
                swap=_dec(d.swap),
                fee=_dec(d.fee),
                profit=_dec(d.profit),
                comment=str(d.comment),
            )
            for d in self._raw_deals(mt5)
        ]

    def _tick_time(self, mt5: Any, symbol: str) -> datetime | None:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None or int(tick.time) <= 0:
            return None
        return _server_time(tick.time)

    def _latest_tick_time(self, mt5: Any, symbol: str | None) -> datetime:
        if symbol is not None:
            if mt5.symbol_info(symbol) is None:
                raise SymbolNotFound(symbol)
            found = self._tick_time(mt5, symbol)
            if found is None:
                raise TerminalNotAvailable(f"no tick available for {symbol}")
            return found

        symbols = mt5.symbols_get()
        if symbols is None and not self._is_ok(mt5):
            raise self._fail(mt5, "cannot read symbols")
        names = [s.name for s in (symbols or ()) if s.visible]
        deals = [d for d in self._raw_deals(mt5) if d.symbol]
        if deals:
            last = max(deals, key=lambda d: (int(d.time), int(getattr(d, "time_msc", 0))))
            if last.symbol not in names:
                names.append(str(last.symbol))
        times = [t for t in (self._tick_time(mt5, name) for name in names) if t is not None]
        if not times:
            self._shutdown(mt5)  # may be a lost session; reconnect on the next call
            raise TerminalNotAvailable("no market data to derive server time")
        return max(times)

    def _rates(self, mt5: Any, symbol: str, timeframe: str, count: int) -> list[Candle]:
        if timeframe not in _TIMEFRAMES:
            raise InvalidTimeframe(timeframe)
        if mt5.symbol_info(symbol) is None or not mt5.symbol_select(symbol, True):
            raise SymbolNotFound(symbol)
        raw = mt5.copy_rates_from_pos(symbol, getattr(mt5, f"TIMEFRAME_{timeframe}"), 0, count)
        if raw is None:
            raise self._fail(mt5, f"cannot read rates for {symbol}")
        return [
            Candle(
                time=_server_time(row["time"]),
                open=_dec(row["open"]),
                high=_dec(row["high"]),
                low=_dec(row["low"]),
                close=_dec(row["close"]),
                tick_volume=int(row["tick_volume"]),
            )
            for row in raw
        ]
