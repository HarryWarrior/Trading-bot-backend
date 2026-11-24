"""Broker server time handling.

MT5 deals and candles carry the broker SERVER time as naive datetimes. The offset to UTC is
measured from the latest tick (server time) against the real UTC clock and rounded to the nearest
30 minutes (real broker offsets are whole or half hours).
"""

from datetime import UTC, datetime, timedelta

_STEP_SECONDS = 30 * 60


def server_offset(latest_tick_server: datetime, utc_now: datetime) -> timedelta:
    if latest_tick_server.tzinfo is not None:
        raise ValueError("latest_tick_server must be naive (broker server time)")
    if utc_now.tzinfo is None:
        raise ValueError("utc_now must be timezone-aware")
    now_naive = utc_now.astimezone(UTC).replace(tzinfo=None)
    seconds = (latest_tick_server - now_naive).total_seconds()
    return timedelta(seconds=round(seconds / _STEP_SECONDS) * _STEP_SECONDS)


def to_utc(server_time: datetime, offset: timedelta) -> datetime:
    if server_time.tzinfo is not None:
        raise ValueError("server_time must be naive (broker server time)")
    return (server_time - offset).replace(tzinfo=UTC)
