from datetime import date
from decimal import Decimal

from builders import make_balance, make_trade, utc

from analytics_service.domain.dataset import Dataset
from analytics_service.domain.series import (
    by_symbol,
    daily,
    equity_curve,
    hourly,
    monthly,
)


def D(value: str) -> Decimal:
    return Decimal(value)


def test_equity_curve_sample(sample_dataset):
    curve = equity_curve(sample_dataset)
    assert [p.equity for p in curve] == [
        D(x) for x in ("200", "250", "100", "700", "600", "760", "1000", "1200", "1150", "1450")
    ]
    assert curve[0].time == utc("2025-01-15 10:45:00")
    assert curve[-1].time == utc("2025-01-18 10:00:00")


def test_equity_curve_with_balance_events():
    dataset = Dataset(
        trades=[make_trade("2025-02-01 10:00:00", "10"), make_trade("2025-02-03 10:00:00", "-50")],
        balance_events=[
            make_balance("2025-01-31 09:00:00", "1000"),
            make_balance("2025-02-02 09:00:00", "500"),
        ],
    )
    assert [p.equity for p in equity_curve(dataset)] == [D("1010"), D("1510"), D("1460")]


def test_equity_curve_empty():
    assert equity_curve(Dataset(trades=[], balance_events=[])) == []


def test_daily_sample(sample_dataset):
    rows = daily(sample_dataset)
    assert [(r.day, r.trades, r.net) for r in rows] == [
        (date(2025, 1, 15), 3, D("100.00")),
        (date(2025, 1, 16), 3, D("660.00")),
        (date(2025, 1, 17), 3, D("390.00")),
        (date(2025, 1, 18), 1, D("300.00")),
    ]


def test_monthly_sample(sample_dataset):
    rows = monthly(sample_dataset)
    assert [(r.month, r.trades, r.net) for r in rows] == [("2025-01", 10, D("1450.00"))]


def test_by_symbol_sample(sample_dataset):
    rows = {r.symbol: r for r in by_symbol(sample_dataset)}
    assert set(rows) == {"EURUSD", "GBPUSD", "USDJPY"}
    eur = rows["EURUSD"]
    assert (eur.trades, eur.wins, eur.net, eur.win_rate) == (5, 2, D("140.00"), D("40.00"))
    assert (rows["GBPUSD"].trades, rows["GBPUSD"].net) == (3, D("510.00"))
    assert (rows["USDJPY"].trades, rows["USDJPY"].net) == (2, D("800.00"))
    assert [r.symbol for r in by_symbol(sample_dataset)] == ["USDJPY", "GBPUSD", "EURUSD"]


def test_hourly_sample(sample_dataset):
    rows = hourly(sample_dataset)
    assert [(r.hour, r.trades, r.net) for r in rows] == [
        (9, 1, D("600.00")),
        (10, 3, D("740.00")),
        (11, 1, D("50.00")),
        (12, 1, D("-100.00")),
        (13, 1, D("200.00")),
        (14, 1, D("160.00")),
        (15, 2, D("-200.00")),
    ]


def test_empty_series():
    empty = Dataset(trades=[], balance_events=[])
    assert daily(empty) == monthly(empty) == by_symbol(empty) == hourly(empty) == []
