from datetime import datetime
from typing import Protocol

from mt5_service.domain.account import TerminalAccount
from mt5_service.domain.deals import Candle, Deal


class BrokerTerminal(Protocol):
    """The MT5 terminal running on this machine. Times are naive broker SERVER time."""

    async def current_account(self) -> TerminalAccount:
        """Raises TerminalNotAvailable."""
        ...

    async def history_deals(self) -> list[Deal]: ...

    async def latest_tick_time(self, symbol: str | None) -> datetime: ...

    async def rates(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        """Raises SymbolNotFound / TerminalNotAvailable."""
        ...
