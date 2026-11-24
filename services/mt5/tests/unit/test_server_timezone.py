"""Broker time converted with a configured IANA zone (DST aware, works on weekends)."""

from datetime import UTC, datetime, timedelta

import pytest
from mt5_fakes import FixedClock, candle, deal

from mt5_service.application.use_cases.get_rates import GetRates
from mt5_service.application.use_cases.link_account import LinkAccount
from mt5_service.application.use_cases.sync_account import SyncAccount
from mt5_service.domain.deals import DealEntry, DealType
from mt5_service.domain.errors import ServerTimezoneMismatch, TerminalNotAvailable
from mt5_service.domain.time import FixedOffsetConverter, ZoneConverter
from mt5_service.domain.trades import build_trades

ATHENS = "Europe/Athens"


def test_zone_converter_applies_the_offset_in_force_at_each_timestamp():
    zone = ZoneConverter(ATHENS)
    assert zone.to_utc(datetime(2026, 1, 15, 15, 0)) == datetime(2026, 1, 15, 13, 0, tzinfo=UTC)
    assert zone.to_utc(datetime(2026, 7, 15, 15, 0)) == datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    assert zone.to_utc(datetime(2026, 7, 15, 15, 0)).utcoffset() == timedelta(0)


def test_ambiguous_and_nonexistent_times_use_fold_zero():
    zone = ZoneConverter(ATHENS)
    # 2026-10-25 03:30 happens twice; fold=0 is the first one (still summer time, +3).
    assert zone.to_utc(datetime(2026, 10, 25, 3, 30)) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    # 2026-03-29 03:30 never happens; fold=0 uses the offset before the jump (+2).
    assert zone.to_utc(datetime(2026, 3, 29, 3, 30)) == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)


def test_zone_converter_rejects_unknown_zone_and_aware_input():
    with pytest.raises(ValueError, match="time zone"):
        ZoneConverter("Mars/Olympus")
    with pytest.raises(ValueError, match="naive"):
        ZoneConverter(ATHENS).to_utc(datetime(2026, 1, 1, tzinfo=UTC))


def test_fixed_offset_converter():
    converter = FixedOffsetConverter(timedelta(hours=3))
    assert converter.to_utc(datetime(2026, 3, 2, 15, 0)) == datetime(2026, 3, 2, 12, 0, tzinfo=UTC)


def test_build_trades_with_zone_converts_each_deal_by_its_own_date():
    deals = [
        deal(1, 1, "2026-01-15T14:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(2, 1, "2026-01-15T15:00:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2"),
        deal(3, 2, "2026-07-15T14:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(4, 2, "2026-07-15T15:00:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2"),
        deal(5, 3, "2026-07-15T16:00:00", DealType.BALANCE, DealEntry.IN, profit="100"),
    ]  # fmt: skip
    result = build_trades(deals, ZoneConverter(ATHENS))
    winter, summer = result.trades
    assert winter.close_time == datetime(2026, 1, 15, 13, 0, tzinfo=UTC)
    assert summer.close_time == datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    assert result.balance_events[0].time == datetime(2026, 7, 15, 13, 0, tzinfo=UTC)


async def test_sync_with_zone_handles_winter_and_summer_deals_in_one_run(
    terminal, journal, repo, ids
):
    clock = FixedClock(datetime(2026, 7, 20, 12, 0, tzinfo=UTC))
    terminal.tick_time = datetime(2026, 7, 20, 15, 0, 5)  # Athens is +3 in July
    account = await LinkAccount(terminal, repo, clock, ids).execute("u1")
    terminal.deals = [
        deal(1, 1, "2026-01-15T14:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(2, 1, "2026-01-15T15:00:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2"),
        deal(3, 2, "2026-07-15T14:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(4, 2, "2026-07-15T15:00:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2"),
    ]  # fmt: skip
    sync = SyncAccount(terminal, journal, repo, clock, server_timezone=ATHENS)
    await sync.execute("u1", account.id, "tok")

    winter, summer = journal.calls[0][2]
    assert winter.close_time == datetime(2026, 1, 15, 13, 0, tzinfo=UTC)
    assert summer.close_time == datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


async def test_sync_with_zone_works_on_a_weekend_with_stale_ticks(
    terminal, journal, repo, clock, ids
):
    account = await LinkAccount(terminal, repo, clock, ids).execute("u1")
    terminal.deals = [
        deal(1, 1, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(2, 1, "2026-03-02T11:00:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2"),
    ]  # fmt: skip
    terminal.tick_time = datetime(2026, 2, 27, 23, 59, 0)  # Friday close, market shut
    await SyncAccount(terminal, journal, repo, clock, server_timezone=ATHENS).execute(
        "u1", account.id, "tok"
    )
    assert journal.calls[0][2][0].open_time == datetime(2026, 3, 2, 8, 0, tzinfo=UTC)


async def test_rates_with_zone_work_on_a_weekend_with_stale_ticks(terminal, clock):
    terminal.tick_time = datetime(2026, 2, 27, 23, 59, 0)
    terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00")]
    result = await GetRates(terminal, clock, server_timezone=ATHENS).execute("EURUSD", "H1", 1)
    assert result[0].time == datetime(2026, 3, 2, 13, 0, tzinfo=UTC)


async def test_rates_with_zone_ignore_a_missing_tick(terminal, clock):
    async def no_tick(symbol):
        raise TerminalNotAvailable("no market data to derive server time")

    terminal.latest_tick_time = no_tick
    terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00")]
    result = await GetRates(terminal, clock, server_timezone=ATHENS).execute("EURUSD", "H1", 1)
    assert result[0].time == datetime(2026, 3, 2, 13, 0, tzinfo=UTC)


async def test_rates_with_zone_win_over_the_fixed_offset_override(terminal, clock):
    terminal.tick_time = datetime(2026, 3, 2, 14, 0, 3)
    terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00")]
    rates = GetRates(terminal, clock, server_utc_offset_minutes=0, server_timezone=ATHENS)
    assert (await rates.execute("EURUSD", "H1", 1))[0].time == datetime(
        2026, 3, 2, 13, 0, tzinfo=UTC
    )


async def test_zone_that_does_not_match_the_live_tick_is_rejected(terminal, clock):
    # Clock 12:00Z, tick 15:00 -> the terminal runs at +3 but Athens is +2 in March.
    terminal.tick_time = datetime(2026, 3, 2, 15, 0, 7)
    terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00")]
    with pytest.raises(ServerTimezoneMismatch) as caught:
        await GetRates(terminal, clock, server_timezone=ATHENS).execute("EURUSD", "H1", 1)
    assert caught.value.code == "SERVER_TIMEZONE_MISMATCH" and caught.value.http_status == 409
    assert "MT5_SERVER_TIMEZONE" in str(caught.value) and ATHENS not in str(caught.value)


async def test_sync_with_mismatching_zone_writes_nothing(terminal, journal, repo, clock, ids):
    account = await LinkAccount(terminal, repo, clock, ids).execute("u1")
    terminal.deals = [
        deal(1, 1, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(2, 1, "2026-03-02T11:00:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2"),
    ]  # fmt: skip
    terminal.tick_time = datetime(2026, 3, 2, 15, 0, 7)
    with pytest.raises(ServerTimezoneMismatch):
        await SyncAccount(terminal, journal, repo, clock, server_timezone=ATHENS).execute(
            "u1", account.id, "tok"
        )
    assert journal.calls == []


async def test_tick_within_ten_minutes_of_the_zone_offset_is_accepted(terminal, clock):
    terminal.tick_time = datetime(2026, 3, 2, 14, 9, 0)  # +2h09m: clock skew tolerated
    terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00")]
    assert await GetRates(terminal, clock, server_timezone=ATHENS).execute("EURUSD", "H1", 1)
