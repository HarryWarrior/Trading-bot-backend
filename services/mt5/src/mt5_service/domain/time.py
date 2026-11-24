"""Broker server time handling.

MT5 deals and candles carry the broker SERVER time as naive datetimes. The offset to UTC is
measured from the latest tick (server time) against the real UTC clock and rounded to the nearest
30 minutes (real broker offsets are whole or half hours).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mt5_service.domain.errors import ServerTimezoneMismatch, TerminalNotAvailable

_STEP_SECONDS = 30 * 60
_MIN_OFFSET = timedelta(hours=-12)
_MAX_OFFSET = timedelta(hours=14)
_MAX_RESIDUAL = timedelta(minutes=10)


def server_offset(latest_tick_server: datetime, utc_now: datetime) -> timedelta:
    if latest_tick_server.tzinfo is not None:
        raise ValueError("latest_tick_server must be naive (broker server time)")
    if utc_now.tzinfo is None:
        raise ValueError("utc_now must be timezone-aware")
    now_naive = utc_now.astimezone(UTC).replace(tzinfo=None)
    seconds = (latest_tick_server - now_naive).total_seconds()
    return timedelta(seconds=round(seconds / _STEP_SECONDS) * _STEP_SECONDS)


def resolve_offset(
    tick_time_server: datetime, utc_now: datetime, override_minutes: int | None
) -> timedelta:
    """Server-to-UTC offset: the configured override, else measured from a fresh tick.

    A measured offset is trusted only if it is a plausible broker offset (-12h..+14h) and the tick
    is fresh (within 10 minutes of the rounded offset); otherwise the market data is stale (e.g.
    weekend) and guessing would shift every stored time, so the terminal is reported unavailable.
    """
    if override_minutes is not None:
        return timedelta(minutes=override_minutes)
    raw = server_offset_raw(tick_time_server, utc_now)
    rounded = server_offset(tick_time_server, utc_now)
    if not _MIN_OFFSET <= rounded <= _MAX_OFFSET or abs(raw - rounded) > _MAX_RESIDUAL:
        raise TerminalNotAvailable("cannot determine broker server time; market data is stale")
    return rounded


def server_offset_raw(latest_tick_server: datetime, utc_now: datetime) -> timedelta:
    if latest_tick_server.tzinfo is not None:
        raise ValueError("latest_tick_server must be naive (broker server time)")
    if utc_now.tzinfo is None:
        raise ValueError("utc_now must be timezone-aware")
    return latest_tick_server - utc_now.astimezone(UTC).replace(tzinfo=None)


def to_utc(server_time: datetime, offset: timedelta) -> datetime:
    if server_time.tzinfo is not None:
        raise ValueError("server_time must be naive (broker server time)")
    return (server_time - offset).replace(tzinfo=UTC)


class TimeConverter(Protocol):
    def to_utc(self, server_time: datetime) -> datetime:
        """Naive broker server time -> timezone-aware UTC."""
        ...


@dataclass(frozen=True)
class FixedOffsetConverter:
    """One constant offset for every timestamp (detected from a tick or configured)."""

    offset: timedelta

    def to_utc(self, server_time: datetime) -> datetime:
        return to_utc(server_time, self.offset)


class ZoneConverter:
    """Converts each timestamp with the offset an IANA zone had AT THAT MOMENT (DST aware).

    Needs no market data, so it also works on weekends. A wall-clock time that happens twice (DST
    fall-back) or never (spring-forward) is resolved with ``fold=0``: the first occurrence / the
    offset in force before the jump.
    """

    def __init__(self, zone_name: str) -> None:
        try:
            self._zone = ZoneInfo(zone_name)
        except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
            raise ValueError(f"unknown time zone {zone_name!r}") from exc

    def to_utc(self, server_time: datetime) -> datetime:
        if server_time.tzinfo is not None:
            raise ValueError("server_time must be naive (broker server time)")
        return server_time.replace(tzinfo=self._zone, fold=0).astimezone(UTC)

    def verify_against_tick(self, tick_time_server: datetime, utc_now: datetime) -> None:
        """Rejects a zone that contradicts the live tick.

        A tick can be older than "now" (market closed, quiet symbol) but never newer, so only a
        tick AHEAD of the zone's current offset by more than 10 minutes proves a mismatch. A zone
        that is too far ahead of the real broker time cannot be told apart from a stale tick.
        """
        now = utc_now.astimezone(UTC)
        zone_offset = now.astimezone(self._zone).utcoffset() or timedelta(0)
        if server_offset_raw(tick_time_server, utc_now) - zone_offset > _MAX_RESIDUAL:
            raise ServerTimezoneMismatch


def as_converter(value: "timedelta | TimeConverter") -> TimeConverter:
    return FixedOffsetConverter(value) if isinstance(value, timedelta) else value
