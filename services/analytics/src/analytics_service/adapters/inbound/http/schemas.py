"""Response models. Decimals leave as JSON numbers with 2 dp, unknowns as null."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from analytics_service.domain import series
from analytics_service.domain.equity import EquityPoint
from analytics_service.domain.summary import Summary


def num(value: Decimal) -> float:
    return float(round(value, 2))


def opt(value: Decimal | None) -> float | None:
    return None if value is None else num(value)


class SummaryOut(BaseModel):
    total_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    profit_factor: float | None
    payoff_ratio: float | None
    average_trade: float | None
    max_drawdown: float
    max_drawdown_pct: float | None
    longest_win_streak: int
    longest_loss_streak: int
    best_day: date | None
    best_day_net: float | None
    worst_day: date | None
    worst_day_net: float | None
    starting_balance: float | None
    ending_balance: float | None

    @classmethod
    def from_domain(cls, s: Summary) -> SummaryOut:
        return cls(
            total_trades=s.total_trades,
            wins=s.wins,
            losses=s.losses,
            breakeven=s.breakeven,
            win_rate=num(s.win_rate),
            gross_profit=num(s.gross_profit),
            gross_loss=num(s.gross_loss),
            net_profit=num(s.net_profit),
            profit_factor=opt(s.profit_factor),
            payoff_ratio=opt(s.payoff_ratio),
            average_trade=opt(s.average_trade),
            max_drawdown=num(s.max_drawdown),
            max_drawdown_pct=opt(s.max_drawdown_pct),
            longest_win_streak=s.longest_win_streak,
            longest_loss_streak=s.longest_loss_streak,
            best_day=s.best_day,
            best_day_net=opt(s.best_day_net),
            worst_day=s.worst_day,
            worst_day_net=opt(s.worst_day_net),
            starting_balance=opt(s.starting_balance),
            ending_balance=opt(s.ending_balance),
        )


class SummaryEnvelope(BaseModel):
    summary: SummaryOut


class EquityPointOut(BaseModel):
    time: datetime
    equity: float

    @classmethod
    def from_domain(cls, p: EquityPoint) -> EquityPointOut:
        return cls(time=p.time, equity=num(p.equity))


class EquityOut(BaseModel):
    points: list[EquityPointOut]


class DayOut(BaseModel):
    day: date
    trades: int
    net: float

    @classmethod
    def from_domain(cls, s: series.DailyStat) -> DayOut:
        return cls(day=s.day, trades=s.trades, net=num(s.net))


class DailyOut(BaseModel):
    days: list[DayOut]


class MonthOut(BaseModel):
    month: str
    trades: int
    net: float

    @classmethod
    def from_domain(cls, s: series.MonthlyStat) -> MonthOut:
        return cls(month=s.month, trades=s.trades, net=num(s.net))


class MonthlyOut(BaseModel):
    months: list[MonthOut]


class SymbolOut(BaseModel):
    symbol: str
    trades: int
    wins: int
    win_rate: float
    net: float

    @classmethod
    def from_domain(cls, s: series.SymbolStat) -> SymbolOut:
        return cls(
            symbol=s.symbol, trades=s.trades, wins=s.wins, win_rate=num(s.win_rate), net=num(s.net)
        )


class BySymbolOut(BaseModel):
    symbols: list[SymbolOut]


class HourOut(BaseModel):
    hour: int
    trades: int
    net: float

    @classmethod
    def from_domain(cls, s: series.HourStat) -> HourOut:
        return cls(hour=s.hour, trades=s.trades, net=num(s.net))


class HourlyOut(BaseModel):
    hours: list[HourOut]
