"""Chooses how broker server time is converted to UTC (shared by sync and rates)."""

from datetime import datetime, timedelta

from mt5_service.application.ports.terminal import BrokerTerminal
from mt5_service.domain.errors import TerminalNotAvailable
from mt5_service.domain.time import (
    FixedOffsetConverter,
    TimeConverter,
    ZoneConverter,
    resolve_offset,
)


async def resolve_converter(
    terminal: BrokerTerminal,
    utc_now: datetime,
    timezone: str | None,
    override_minutes: int | None,
) -> TimeConverter:
    """A configured IANA zone wins (DST aware, no ticks needed); it is only sanity-checked against
    the live tick when one is available. Without a zone: the fixed override, else the offset
    detected from the latest tick."""
    if timezone:
        zone = ZoneConverter(timezone)
        try:
            tick = await terminal.latest_tick_time(None)
        except TerminalNotAvailable:
            return zone  # no market data to cross-check; the zone does not need it
        zone.verify_against_tick(tick, utc_now)
        return zone
    if override_minutes is not None:
        return FixedOffsetConverter(timedelta(minutes=override_minutes))
    tick = await terminal.latest_tick_time(None)
    return FixedOffsetConverter(resolve_offset(tick, utc_now, None))
