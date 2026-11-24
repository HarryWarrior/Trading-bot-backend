from datetime import date
from decimal import Decimal

from builders import make_balance, make_trade

from analytics_service.domain.dataset import Dataset
from analytics_service.domain.rounding import round_money
from analytics_service.domain.summary import summarize


def D(value: str) -> Decimal:
    return Decimal(value)


def test_round_money_half_up():
    assert round_money(Decimal("2.345")) == D("2.35")
    assert round_money(Decimal("-2.345")) == D("-2.35")
    assert round_money(Decimal("5.8333333")) == D("5.83")
    assert str(round_money(Decimal("1"))) == "1.00"


def test_sample_summary(sample_dataset):
    s = summarize(sample_dataset)
    assert (s.total_trades, s.wins, s.losses, s.breakeven) == (10, 7, 3, 0)
    assert s.win_rate == D("70.00")
    assert s.gross_profit == D("1750.00")
    assert s.gross_loss == D("-300.00")
    assert s.net_profit == D("1450.00")
    assert s.profit_factor == D("5.83")
    assert s.payoff_ratio == D("2.50")
    assert s.average_trade == D("145.00")
    assert s.max_drawdown == D("-150.00")
    assert s.max_drawdown_pct is None
    assert s.starting_balance is None
    assert s.ending_balance is None
    assert s.longest_win_streak == 3
    assert s.longest_loss_streak == 1
    assert s.best_day == date(2025, 1, 16)
    assert s.best_day_net == D("660.00")
    assert s.worst_day == date(2025, 1, 15)
    assert s.worst_day_net == D("100.00")


def test_with_starting_balance():
    dataset = Dataset(
        trades=[make_trade("2025-02-01 10:00:00", "10"), make_trade("2025-02-02 10:00:00", "-400")],
        balance_events=[make_balance("2025-01-31 09:00:00", "1000")],
    )
    s = summarize(dataset)
    assert s.max_drawdown == D("-400.00")
    assert s.max_drawdown_pct == D("-39.60")
    assert D("-100") <= s.max_drawdown_pct <= D("0")
    assert s.starting_balance == D("1000.00")
    assert s.ending_balance == D("610.00")
    assert s.net_profit == D("-390.00")


def test_mid_way_deposit_is_not_profit():
    dataset = Dataset(
        trades=[make_trade("2025-02-01 10:00:00", "100"), make_trade("2025-02-03 10:00:00", "-50")],
        balance_events=[
            make_balance("2025-01-31 09:00:00", "1000"),
            make_balance("2025-02-02 09:00:00", "500"),
        ],
    )
    s = summarize(dataset)
    assert s.net_profit == D("50.00")
    assert s.starting_balance == D("1000.00")
    assert s.ending_balance == D("1550.00")
    # The deposit shifts equity and peak to 1600; the -50 loss is measured from there.
    assert s.max_drawdown == D("-50.00")
    assert s.max_drawdown_pct == D("-3.13")


def test_withdrawal_is_neither_drawdown_nor_profit():
    dataset = Dataset(
        trades=[make_trade("2025-02-01 10:00:00", "100")],
        balance_events=[
            make_balance("2025-01-31 09:00:00", "1000"),
            make_balance("2025-02-02 09:00:00", "-300"),
        ],
    )
    s = summarize(dataset)
    assert s.net_profit == D("100.00")
    assert s.ending_balance == D("800.00")
    assert s.max_drawdown == D("0.00")
    assert s.max_drawdown_pct == D("0.00")


def test_large_withdrawal_after_profit_is_not_drawdown():
    # deposit 1000, +1000, withdraw 1500, +10: no trade lost money.
    dataset = Dataset(
        trades=[make_trade("2025-02-01 10:00:00", "1000"), make_trade("2025-02-03 10:00:00", "10")],
        balance_events=[
            make_balance("2025-01-31 09:00:00", "1000"),
            make_balance("2025-02-02 09:00:00", "-1500"),
        ],
    )
    s = summarize(dataset)
    assert s.max_drawdown == D("0.00")
    assert s.max_drawdown_pct == D("0.00")
    assert s.starting_balance == D("1000.00")
    assert s.ending_balance == D("510.00")
    assert s.net_profit == D("1010.00")


def test_loss_after_withdrawal_is_measured_from_shifted_peak():
    # 1000 -> -100 (900, dd -100 / -10%) -> +600 (1500 peak) -> withdraw 1000 (500, peak 500)
    # -> -200 (300, dd -200 on peak 500 = -40%). The old walk reported -1200 / -80%.
    dataset = Dataset(
        trades=[
            make_trade("2025-02-01 10:00:00", "-100"),
            make_trade("2025-02-02 10:00:00", "600"),
            make_trade("2025-02-04 10:00:00", "-200"),
        ],
        balance_events=[
            make_balance("2025-01-31 09:00:00", "1000"),
            make_balance("2025-02-03 09:00:00", "-1000"),
        ],
    )
    s = summarize(dataset)
    assert s.max_drawdown == D("-200.00")
    assert s.max_drawdown_pct == D("-40.00")
    assert s.ending_balance == D("300.00")
    assert s.net_profit == D("300.00")


def test_balance_before_trade_on_equal_timestamps():
    dataset = Dataset(
        trades=[make_trade("2025-02-01 10:00:00", "100")],
        balance_events=[make_balance("2025-02-01 10:00:00", "1000")],
    )
    s = summarize(dataset)
    assert s.starting_balance == D("1000.00")
    assert s.ending_balance == D("1100.00")


def test_empty_dataset():
    s = summarize(Dataset(trades=[], balance_events=[]))
    assert (s.total_trades, s.wins, s.losses, s.breakeven) == (0, 0, 0, 0)
    assert s.win_rate == D("0.00")
    assert s.gross_profit == D("0.00")
    assert s.gross_loss == D("0.00")
    assert s.net_profit == D("0.00")
    assert s.max_drawdown == D("0.00")
    assert s.longest_win_streak == 0
    assert s.longest_loss_streak == 0
    for field in (
        "profit_factor",
        "payoff_ratio",
        "average_trade",
        "max_drawdown_pct",
        "best_day",
        "best_day_net",
        "worst_day",
        "worst_day_net",
        "starting_balance",
        "ending_balance",
    ):
        assert getattr(s, field) is None, field


def test_all_wins_have_no_ratios():
    dataset = Dataset(
        trades=[make_trade("2025-02-01 10:00:00", "10"), make_trade("2025-02-02 10:00:00", "20")],
        balance_events=[],
    )
    s = summarize(dataset)
    assert s.profit_factor is None
    assert s.payoff_ratio is None
    assert s.max_drawdown == D("0.00")
    assert s.longest_win_streak == 2


def test_all_losses_have_no_payoff():
    dataset = Dataset(trades=[make_trade("2025-02-01 10:00:00", "-10")], balance_events=[])
    s = summarize(dataset)
    assert s.profit_factor == D("0.00")
    assert s.payoff_ratio is None
    assert s.longest_loss_streak == 1


def test_breakeven_breaks_streaks_and_is_counted():
    nets = ["10", "10", "0", "10", "-5", "0", "-5", "-5"]
    trades = [make_trade(f"2025-02-0{i + 1} 10:00:00", n) for i, n in enumerate(nets)]
    s = summarize(Dataset(trades=trades, balance_events=[]))
    assert s.breakeven == 2
    assert s.longest_win_streak == 2
    assert s.longest_loss_streak == 2
    assert s.win_rate == D("37.50")


def test_streaks_follow_close_time_not_input_order():
    trades = [
        make_trade("2025-02-03 10:00:00", "10"),
        make_trade("2025-02-01 10:00:00", "10"),
        make_trade("2025-02-02 10:00:00", "-10"),
    ]
    s = summarize(Dataset(trades=trades, balance_events=[]))
    assert s.longest_win_streak == 1


def test_drawdown_pct_none_when_peak_not_positive():
    dataset = Dataset(
        trades=[make_trade("2025-02-01 10:00:00", "-10")],
        balance_events=[make_balance("2025-01-31 09:00:00", "0")],
    )
    s = summarize(dataset)
    assert s.starting_balance == D("0.00")
    assert s.max_drawdown == D("-10.00")
    assert s.max_drawdown_pct is None


def test_balance_only_dataset():
    s = summarize(Dataset(trades=[], balance_events=[make_balance("2025-01-31 09:00:00", "250")]))
    assert s.total_trades == 0
    assert s.starting_balance == D("250.00")
    assert s.ending_balance == D("250.00")
    assert s.max_drawdown == D("0.00")
