from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from mt5_fakes import closed_position_deals, deal

from mt5_service.domain.deals import DealEntry, DealType
from mt5_service.domain.time import server_offset, to_utc
from mt5_service.domain.trades import build_trades

D = Decimal
PLUS_2H = timedelta(hours=2)


def test_offset_rounds_to_30_minutes():
    offset = server_offset(
        datetime(2026, 3, 2, 15, 0, 7), datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)
    )
    assert offset == timedelta(hours=3)


def test_offset_supports_half_hours_and_negative():
    now = datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)
    assert server_offset(datetime(2026, 3, 2, 17, 31, 0), now) == timedelta(hours=5, minutes=30)
    assert server_offset(datetime(2026, 3, 2, 7, 0, 3), now) == timedelta(hours=-5)


def test_to_utc_converts_server_time():
    result = to_utc(datetime(2026, 3, 2, 15, 0, 0), timedelta(hours=3))
    assert result == datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)
    assert result.utcoffset() == timedelta(0)


def test_single_entry_exit_builds_trade():
    result = build_trades(closed_position_deals(position_id=7), PLUS_2H)

    assert result.open_positions == 0
    assert result.skipped_positions == []
    [trade] = result.trades
    assert trade.position_id == "7"
    assert trade.side == "buy"
    assert trade.volume == D("1.0")
    assert trade.open_price == D("1.1000")
    assert trade.close_price == D("1.1050")
    assert trade.open_time == datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    assert trade.close_time == datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
    assert trade.profit == D("50")
    assert trade.commission == D("-4")
    assert trade.swap == D("0")
    assert trade.profit + trade.commission + trade.swap == D("46")


def test_sell_position_and_fee_folded_into_commission():
    deals = [
        deal(1, 9, "2026-03-02T10:00:00", DealType.SELL, DealEntry.IN, volume="0.5", price="1.2"),
        deal(2, 9, "2026-03-02T10:30:00", DealType.BUY, DealEntry.OUT, volume="0.5", price="1.19",
             profit="50", commission="-1", swap="-0.5", fee="-0.25", comment="tp"),
    ]  # fmt: skip
    [trade] = build_trades(deals, PLUS_2H).trades
    assert trade.side == "sell"
    assert trade.commission == D("-1.25")
    assert trade.swap == D("-0.5")


def test_partial_exits_aggregate():
    deals = [
        deal(1, 5, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1.0", price="1.1000",
             commission="-2"),
        deal(2, 5, "2026-03-02T11:00:00", DealType.SELL, DealEntry.OUT, volume="0.4", price="1.1100",
             profit="40", commission="-1", swap="-0.1"),
        deal(3, 5, "2026-03-02T12:00:00", DealType.SELL, DealEntry.OUT, volume="0.6", price="1.1200",
             profit="120", commission="-1.5", swap="-0.2"),
    ]  # fmt: skip
    result = build_trades(deals, PLUS_2H)

    [trade] = result.trades
    assert trade.volume == D("1.0")
    assert trade.close_price == D("1.1160")
    assert trade.close_time == datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    assert trade.open_time == datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    assert trade.profit == D("160")
    assert trade.commission == D("-4.5")
    assert trade.swap == D("-0.3")


def test_open_position_not_sent_and_counted():
    deals = closed_position_deals(position_id=7) + [
        deal(10, 8, "2026-03-02T13:00:00", DealType.BUY, DealEntry.IN, volume="1.0", price="1.3"),
        deal(11, 9, "2026-03-02T13:00:00", DealType.BUY, DealEntry.IN, volume="1.0", price="1.3"),
        deal(12, 9, "2026-03-02T14:00:00", DealType.SELL, DealEntry.OUT, volume="0.3", price="1.31"),
    ]  # fmt: skip
    result = build_trades(deals, PLUS_2H)

    assert [t.position_id for t in result.trades] == ["7"]
    assert result.open_positions == 2


def test_out_by_deal_closes_position():
    deals = [
        deal(1, 4, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(2, 4, "2026-03-02T10:10:00", DealType.SELL, DealEntry.OUT_BY, volume="1", price="1.2",
             profit="10"),
    ]  # fmt: skip
    assert len(build_trades(deals, PLUS_2H).trades) == 1


def test_inout_reversal_is_skipped_with_reason():
    deals = [
        deal(1, 3, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(2, 3, "2026-03-02T10:10:00", DealType.SELL, DealEntry.INOUT, volume="2", price="1.2"),
    ]  # fmt: skip
    result = build_trades(deals, PLUS_2H)

    assert result.trades == []
    assert result.open_positions == 0
    [(position_id, reason)] = result.skipped_positions
    assert position_id == "3"
    assert "INOUT" in reason


def test_exit_without_entry_in_history_is_skipped():
    deals = [
        deal(2, 3, "2026-03-02T10:10:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2")
    ]
    result = build_trades(deals, PLUS_2H)
    assert result.trades == []
    assert [p for p, _ in result.skipped_positions] == ["3"]


def test_balance_deals_map_to_events():
    deals = [
        deal(1, 0, "2026-03-01T09:00:00", DealType.BALANCE, DealEntry.IN, profit="1000", comment="dep"),
        deal(2, 0, "2026-03-01T10:00:00", DealType.BALANCE, DealEntry.OUT, profit="-200"),
        deal(3, 0, "2026-03-01T11:00:00", DealType.CREDIT, DealEntry.IN, profit="50"),
        deal(4, 0, "2026-03-01T12:00:00", DealType.CORRECTION, DealEntry.IN, profit="-3.5"),
        deal(5, 0, "2026-03-01T13:00:00", DealType.COMMISSION, DealEntry.IN, commission="-1", fee="-0.5"),
        deal(6, 0, "2026-03-01T14:00:00", DealType.BUY_CANCELED, DealEntry.IN, profit="9"),
    ]  # fmt: skip
    result = build_trades(deals, PLUS_2H)

    assert result.trades == []
    kinds = [(e.kind, e.amount, e.source_ref) for e in result.balance_events]
    assert kinds == [
        ("deposit", D("1000"), "1"),
        ("withdrawal", D("-200"), "2"),
        ("credit", D("50"), "3"),
        ("adjustment", D("-3.5"), "4"),
        ("adjustment", D("-1.5"), "5"),
    ]
    first = result.balance_events[0]
    assert first.time == datetime(2026, 3, 1, 7, 0, tzinfo=UTC)
    assert first.comment == "dep"
    assert result.balance_events[1].comment is None


def test_payloads_match_journal_ingest_schema():
    result = build_trades(
        closed_position_deals()
        + [deal(50, 0, "2026-03-01T09:00:00", DealType.BALANCE, DealEntry.IN, profit="100")],
        PLUS_2H,
    )
    trade_payload = result.trades[0].to_payload()
    assert trade_payload["side"] == "buy"
    assert trade_payload["open_time"] == "2026-03-02T08:00:00+00:00"
    assert trade_payload["volume"] == "1.0"
    assert set(trade_payload) == {
        "position_id", "symbol", "side", "volume", "open_time", "close_time", "open_price",
        "close_price", "stop_loss", "take_profit", "commission", "swap", "profit", "comment",
    }  # fmt: skip
    event_payload = result.balance_events[0].to_payload()
    assert set(event_payload) == {"kind", "amount", "time", "source_ref", "comment"}
    assert event_payload["amount"] == "100"


def test_naive_inputs_required():
    with pytest.raises(ValueError):
        to_utc(datetime(2026, 3, 2, tzinfo=UTC), timedelta(0))
    with pytest.raises(ValueError):
        server_offset(datetime(2026, 3, 2), datetime(2026, 3, 2))


def test_zero_amount_adjustment_is_skipped():

    result = build_trades(
        [deal(1, 0, "2026-03-02T10:00:00", DealType.CORRECTION, DealEntry.IN)], timedelta(0)
    )
    assert result.balance_events == []


def test_weighted_close_price_is_quantized_to_ten_decimals():

    deals = [
        deal(1, 5, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="3", price="1.1"),
        deal(2, 5, "2026-03-02T11:00:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.1"),
        deal(3, 5, "2026-03-02T11:05:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2"),
        deal(4, 5, "2026-03-02T11:10:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2"),
    ]
    trade = build_trades(deals, timedelta(0)).trades[0]
    assert trade.close_price == Decimal("1.1666666667")
    assert trade.open_price == Decimal("1.1")
