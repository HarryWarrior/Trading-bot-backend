"""Broker server time handling.

MT5 deals and candles carry the broker SERVER time as naive datetimes. The offset to UTC is
measured from the latest tick (server time) against the real UTC clock and rounded to the nearest
30 minutes (real broker offsets are whole or half hours).
"""

from datetime import UTC, datetime, timedelta

from mt5_service.domain.errors import TerminalNotAvailable

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
