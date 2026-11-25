from datetime import UTC, datetime, timedelta

import pytest

from mt5_service.domain.errors import TerminalNotAvailable
from mt5_service.domain.time import resolve_offset

NOW = datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)


def test_fresh_tick_gives_rounded_offset():
    assert resolve_offset(datetime(2026, 3, 2, 15, 0, 7), NOW, None) == timedelta(hours=3)


def test_half_hour_offset_is_supported():
    assert resolve_offset(datetime(2026, 3, 2, 17, 30, 2), NOW, None) == timedelta(
        hours=5, minutes=30
    )


def test_tick_ten_minutes_off_is_still_accepted():
    assert resolve_offset(datetime(2026, 3, 2, 15, 10, 0), NOW, None) == timedelta(hours=3)


def test_stale_tick_is_rejected():
    # 15 min off the nearest half hour -> reject
    with pytest.raises(TerminalNotAvailable, match="market data is stale"):
        resolve_offset(datetime(2026, 3, 2, 14, 15, 0), NOW, None)


def test_weekend_style_stale_tick_is_rejected():
    with pytest.raises(TerminalNotAvailable, match="cannot determine broker server time"):
        resolve_offset(datetime(2026, 2, 27, 23, 59, 0), NOW, None)


@pytest.mark.parametrize("hours", [-13, 15])
def test_offset_outside_real_range_is_rejected(hours):
    tick = datetime(2026, 3, 2, 12, 0, 0) + timedelta(hours=hours)
    with pytest.raises(TerminalNotAvailable):
        resolve_offset(tick, NOW, None)


@pytest.mark.parametrize("hours", [-12, 14])
def test_range_bounds_are_inclusive(hours):
    tick = datetime(2026, 3, 2, 12, 0, 0) + timedelta(hours=hours)
    assert resolve_offset(tick, NOW, None) == timedelta(hours=hours)


def test_override_wins_even_with_stale_tick():
    stale = datetime(2026, 2, 27, 23, 59, 0)
    assert resolve_offset(stale, NOW, 120) == timedelta(hours=2)


def test_override_zero_is_respected():
    assert resolve_offset(datetime(2026, 3, 2, 15, 0, 0), NOW, 0) == timedelta(0)
