"""Pairing of raw MT5 deals into trades; cases ported from the ``mt5`` service trade builder."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from journal_service.domain.deal_pairing import pair_deals
from journal_service.domain.deals import DealEntry, DealType, RawDeal
from journal_service.domain.trade import Side

D = Decimal


def deal(
    ticket: int,
    position_id: int,
    time: str,
    type: int,
    entry: int,
    *,
    volume: str = "0",
    price: str = "0",
    profit: str = "0",
    commission: str = "0",
    swap: str = "0",
    fee: str = "0",
    symbol: str = "EURUSD",
    comment: str = "",
) -> RawDeal:
    return RawDeal(
        ticket=ticket,
        position_id=position_id,
        time=datetime.fromisoformat(time).replace(tzinfo=UTC),
        type=type,
        entry=entry,
        symbol=symbol,
        volume=D(volume),
        price=D(price),
        commission=D(commission),
        swap=D(swap),
        profit=D(profit),
        sl=None,
        tp=None,
        comment=comment,
        fee=D(fee),
    )


def closed_position(position_id: int = 1) -> list[RawDeal]:
    return [
        deal(position_id * 10, position_id, "2026-03-02T08:00:00", DealType.BUY, DealEntry.IN,
             volume="1.0", price="1.1000", commission="-2", comment="entry"),
        deal(position_id * 10 + 1, position_id, "2026-03-02T09:00:00", DealType.SELL,
             DealEntry.OUT, volume="1.0", price="1.1050", profit="50", commission="-2"),
    ]  # fmt: skip


def test_single_entry_exit_builds_trade():
    result = pair_deals(closed_position(7))

    assert result.skipped == []
    [trade] = result.trades
    assert trade.position_id == "7"
    assert trade.side is Side.BUY
    assert trade.volume == D("1.0")
    assert trade.open_price == D("1.1000")
    assert trade.close_price == D("1.1050")
    assert trade.open_time == datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    assert trade.close_time == datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
    assert trade.profit == D("50")
    assert trade.commission == D("-4")
    assert trade.swap == D("0")
    assert trade.comment == "entry"


def test_sell_position_and_fee_folded_into_commission():
    deals = [
        deal(1, 9, "2026-03-02T10:00:00", DealType.SELL, DealEntry.IN, volume="0.5", price="1.2"),
        deal(2, 9, "2026-03-02T10:30:00", DealType.BUY, DealEntry.OUT, volume="0.5", price="1.19",
             profit="50", commission="-1", swap="-0.5", fee="-0.25", comment="tp"),
    ]  # fmt: skip
    [trade] = pair_deals(deals).trades
    assert trade.side is Side.SELL
    assert trade.commission == D("-1.25")
    assert trade.swap == D("-0.5")


def test_partial_exits_aggregate_once_fully_closed():
    deals = [
        deal(1, 5, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1.0", price="1.1000",
             commission="-2"),
        deal(2, 5, "2026-03-02T11:00:00", DealType.SELL, DealEntry.OUT, volume="0.4", price="1.1100",
             profit="40", commission="-1", swap="-0.1"),
        deal(3, 5, "2026-03-02T12:00:00", DealType.SELL, DealEntry.OUT, volume="0.6", price="1.1200",
             profit="120", commission="-1.5", swap="-0.2"),
    ]  # fmt: skip
    [trade] = pair_deals(deals).trades
    assert trade.volume == D("1.0")
    assert trade.close_price == D("1.1160")
    assert trade.close_time == datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    assert trade.profit == D("160")
    assert trade.commission == D("-4.5")
    assert trade.swap == D("-0.3")


def test_partial_exit_stays_open_and_is_counted():
    deals = closed_position(7) + [
        deal(100, 8, "2026-03-02T13:00:00", DealType.BUY, DealEntry.IN, volume="1.0", price="1.3"),
        deal(110, 9, "2026-03-02T13:00:00", DealType.BUY, DealEntry.IN, volume="1.0", price="1.3"),
        deal(120, 9, "2026-03-02T14:00:00", DealType.SELL, DealEntry.OUT, volume="0.3", price="1.31"),
    ]  # fmt: skip
    result = pair_deals(deals)

    assert [t.position_id for t in result.trades] == ["7"]
    assert result.open_positions == 2
    assert result.skipped == []


def test_out_by_deal_closes_position():
    deals = [
        deal(1, 4, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(2, 4, "2026-03-02T10:10:00", DealType.SELL, DealEntry.OUT_BY, volume="1", price="1.2",
             profit="10"),
    ]  # fmt: skip
    assert len(pair_deals(deals).trades) == 1


def test_inout_reversal_is_skipped_with_reason():
    deals = [
        deal(1, 3, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(2, 3, "2026-03-02T10:10:00", DealType.SELL, DealEntry.INOUT, volume="2", price="1.2"),
    ]  # fmt: skip
    result = pair_deals(deals)

    assert result.trades == []
    assert result.open_positions == 0
    [(position_id, reason)] = result.skipped
    assert position_id == "3"
    assert "INOUT" in reason


def test_exit_without_entry_is_skipped():
    deals = [
        deal(2, 3, "2026-03-02T10:10:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2")
    ]
    result = pair_deals(deals)
    assert result.trades == []
    assert [p for p, _ in result.skipped] == ["3"]


def test_balance_deals_map_to_events_and_cancels_are_ignored():
    deals = [
        deal(1, 0, "2026-03-01T09:00:00", DealType.BALANCE, DealEntry.IN, profit="1000", comment="dep"),
        deal(2, 0, "2026-03-01T10:00:00", DealType.BALANCE, DealEntry.OUT, profit="-200"),
        deal(3, 0, "2026-03-01T11:00:00", DealType.CREDIT, DealEntry.IN, profit="50"),
        deal(4, 0, "2026-03-01T12:00:00", DealType.CORRECTION, DealEntry.IN, profit="-3.5"),
        deal(5, 0, "2026-03-01T13:00:00", DealType.COMMISSION, DealEntry.IN, commission="-1", fee="-0.5"),
        deal(6, 0, "2026-03-01T14:00:00", DealType.BUY_CANCELED, DealEntry.IN, profit="9"),
        deal(7, 0, "2026-03-01T15:00:00", DealType.SELL_CANCELED, DealEntry.IN, profit="9"),
    ]  # fmt: skip
    result = pair_deals(deals)

    assert result.trades == []
    assert result.skipped == []
    kinds = [(e.kind, e.amount, e.source_ref) for e in result.balance_events]
    assert kinds == [
        ("deposit", D("1000"), "1"),
        ("withdrawal", D("-200"), "2"),
        ("credit", D("50"), "3"),
        ("adjustment", D("-3.5"), "4"),
        ("adjustment", D("-1.5"), "5"),
    ]
    first = result.balance_events[0]
    assert first.time == datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    assert first.comment == "dep"
    assert result.balance_events[1].comment is None


def test_zero_amount_adjustment_and_zero_balance_are_skipped():
    result = pair_deals(
        [
            deal(1, 0, "2026-03-02T10:00:00", DealType.CORRECTION, DealEntry.IN),
            deal(2, 0, "2026-03-02T10:00:00", DealType.BALANCE, DealEntry.IN),
        ]
    )
    assert result.balance_events == []


def test_weighted_close_price_is_quantized_to_ten_decimals():
    deals = [
        deal(1, 5, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="3", price="1.1"),
        deal(2, 5, "2026-03-02T11:00:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.1"),
        deal(3, 5, "2026-03-02T11:05:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2"),
        deal(4, 5, "2026-03-02T11:10:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.2"),
    ]
    trade = pair_deals(deals).trades[0]
    assert trade.close_price == D("1.1666666667")
    assert trade.open_price == D("1.1")


def test_unknown_deal_type_becomes_adjustment_and_zero_is_skipped():
    result = pair_deals(
        [
            deal(1, 0, "2026-03-02T10:00:00", DealType.BALANCE, DealEntry.IN, profit="1"),
            deal(2, 0, "2026-03-02T10:01:00", 99, DealEntry.IN, profit="5", commission="-1"),
            deal(3, 0, "2026-03-02T10:02:00", 98, DealEntry.IN),
        ]
    )
    kinds = [(e.kind, e.amount) for e in result.balance_events]
    assert kinds == [("deposit", D("1")), ("adjustment", D("4"))]


def test_unknown_entry_on_trade_deal_skips_position_with_reason():
    deals = closed_position(7) + [
        deal(90, 8, "2026-03-02T12:00:00", DealType.BUY, 9, volume="1", price="1.1")
    ]
    result = pair_deals(deals)
    assert [t.position_id for t in result.trades] == ["7"]
    assert result.skipped == [("8", "unknown deal entry 9")]


def test_mixed_entry_sides_skip_the_position_with_reason():
    deals = [
        deal(1, 6, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1.0", price="1.1"),
        deal(2, 6, "2026-03-02T10:30:00", DealType.SELL, DealEntry.IN, volume="0.5", price="1.1"),
        deal(3, 6, "2026-03-02T11:00:00", DealType.SELL, DealEntry.OUT, volume="1.5", price="1.1"),
    ]  # fmt: skip
    result = pair_deals(deals)
    assert result.trades == []
    assert result.skipped == [("6", "mixed entry sides")]


def test_exit_volume_exceeding_entry_is_skipped():
    deals = [
        deal(1, 6, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1.0", price="1.1"),
        deal(2, 6, "2026-03-02T11:00:00", DealType.SELL, DealEntry.OUT, volume="2.0", price="1.1"),
    ]  # fmt: skip
    assert pair_deals(deals).skipped == [("6", "exit volume exceeds entry volume")]


def test_multiple_entries_of_the_same_side_use_weighted_open_price():
    deals = [
        deal(1, 6, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1.0", price="1.1000"),
        deal(2, 6, "2026-03-02T10:30:00", DealType.BUY, DealEntry.IN, volume="3.0", price="1.2000"),
        deal(3, 6, "2026-03-02T11:00:00", DealType.SELL, DealEntry.OUT, volume="4.0", price="1.3"),
    ]  # fmt: skip
    [trade] = pair_deals(deals).trades
    assert trade.volume == D("4.0")
    assert trade.open_price == D("1.175")
    assert trade.side is Side.BUY
    assert trade.open_time == datetime(2026, 3, 2, 10, 0, tzinfo=UTC)


def test_exit_before_entry_in_batch_pairs_once_both_present():
    entry, exit_ = closed_position(7)

    only_exit = pair_deals([exit_])
    assert only_exit.trades == []

    [trade] = pair_deals([exit_, entry]).trades
    assert trade.side is Side.BUY
    assert trade.open_time == datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    assert trade.close_time == datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def test_stop_loss_and_take_profit_come_from_the_entry_deal():
    entry, exit_ = closed_position(7)
    entry = RawDeal(**{**entry.__dict__, "sl": D("1.09"), "tp": D("1.12")})
    [trade] = pair_deals([entry, exit_]).trades
    assert (trade.stop_loss, trade.take_profit) == (D("1.09"), D("1.12"))


def test_raw_deal_requires_aware_time():
    with pytest.raises(ValueError):
        RawDeal(
            ticket=1, position_id=1, time=datetime(2026, 1, 1), type=0, entry=0, symbol="X",
            volume=D(1), price=D(1), commission=D(0), swap=D(0), profit=D(0),
            sl=None, tp=None, comment=None,
        )  # fmt: skip


def test_zero_volume_trade_deals_are_skipped_not_raised():
    deals = [
        deal(1, 6, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="0", price="1.1"),
        deal(2, 6, "2026-03-02T11:00:00", DealType.SELL, DealEntry.OUT, volume="0", price="1.2"),
    ]  # fmt: skip
    result = pair_deals(deals + closed_position(7))
    assert [t.position_id for t in result.trades] == ["7"]
    assert result.skipped == [("6", "non-positive deal volume")]
