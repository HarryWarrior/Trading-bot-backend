from dataclasses import replace

from mt5_service.application.ports.clock import Clock
from mt5_service.application.ports.terminal import BrokerTerminal
from mt5_service.application.server_time import resolve_converter
from mt5_service.domain.deals import Candle
from mt5_service.domain.errors import CountOutOfRange, InvalidTimeframe

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
MAX_COUNT = 1000


class GetRates:
    def __init__(
        self,
        terminal: BrokerTerminal,
        clock: Clock,
        server_utc_offset_minutes: int | None = None,
        server_timezone: str | None = None,
    ) -> None:
        self._terminal = terminal
        self._clock = clock
        self._offset_override = server_utc_offset_minutes
        self._timezone = server_timezone

    async def execute(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        if timeframe not in TIMEFRAMES:
            raise InvalidTimeframe(timeframe)
        if not 1 <= count <= MAX_COUNT:
            raise CountOutOfRange(count, MAX_COUNT)
        candles = await self._terminal.rates(symbol, timeframe, count)
        converter = await resolve_converter(
            self._terminal, self._clock.now(), self._timezone, self._offset_override
        )
        return [replace(c, time=converter.to_utc(c.time)) for c in candles]
