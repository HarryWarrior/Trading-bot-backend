"""Headline KPIs of a dataset. Everything is computed on net results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal

from analytics_service.domain.dataset import Dataset
from analytics_service.domain.equity import ZERO, walk_equity
from analytics_service.domain.rounding import round_money

HUNDRED = Decimal(100)


@dataclass(frozen=True)
class Summary:
    total_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    net_profit: Decimal
    profit_factor: Decimal | None
    payoff_ratio: Decimal | None
    average_trade: Decimal | None
    max_drawdown: Decimal
    max_drawdown_pct: Decimal | None
    longest_win_streak: int
    longest_loss_streak: int
    best_day: date | None
    best_day_net: Decimal | None
    worst_day: date | None
    worst_day_net: Decimal | None
    starting_balance: Decimal | None
    ending_balance: Decimal | None


def _longest_streaks(nets: list[Decimal]) -> tuple[int, int]:
    best_win = best_loss = win = loss = 0
    for net in nets:
        win = win + 1 if net > 0 else 0
        loss = loss + 1 if net < 0 else 0
        best_win = max(best_win, win)
        best_loss = max(best_loss, loss)
    return best_win, best_loss


def _optional(value: Decimal | None) -> Decimal | None:
    return None if value is None else round_money(value)


def summarize(dataset: Dataset) -> Summary:
    trades = dataset.ordered_trades()
    nets = [trade.net for trade in trades]
    winners = [n for n in nets if n > 0]
    losers = [n for n in nets if n < 0]
    total = len(nets)

    gross_profit = sum(winners, ZERO)
    gross_loss = sum(losers, ZERO)
    net_profit = gross_profit + gross_loss

    profit_factor = gross_profit / -gross_loss if gross_loss != 0 else None
    payoff = None
    if winners and losers:
        payoff = (gross_profit / len(winners)) / (-gross_loss / len(losers))

    per_day: dict[date, Decimal] = {}
    for trade in trades:
        day = trade.close_time.astimezone(UTC).date()
        per_day[day] = per_day.get(day, ZERO) + trade.net
    # Ties resolve to the earliest day.
    best_day = min(per_day, key=lambda d: (-per_day[d], d)) if per_day else None
    worst_day = min(per_day, key=lambda d: (per_day[d], d)) if per_day else None

    walk = walk_equity(dataset)
    drawdown_pct = None
    if walk.starting_balance is not None and walk.max_drawdown_peak > 0:
        drawdown_pct = walk.max_drawdown / walk.max_drawdown_peak * HUNDRED

    win_streak, loss_streak = _longest_streaks(nets)
    return Summary(
        total_trades=total,
        wins=len(winners),
        losses=len(losers),
        breakeven=total - len(winners) - len(losers),
        win_rate=round_money(Decimal(len(winners)) / total * HUNDRED if total else ZERO),
        gross_profit=round_money(gross_profit),
        gross_loss=round_money(gross_loss),
        net_profit=round_money(net_profit),
        profit_factor=_optional(profit_factor),
        payoff_ratio=_optional(payoff),
        average_trade=round_money(net_profit / total) if total else None,
        max_drawdown=round_money(walk.max_drawdown),
        max_drawdown_pct=_optional(drawdown_pct),
        longest_win_streak=win_streak,
        longest_loss_streak=loss_streak,
        best_day=best_day,
        best_day_net=_optional(per_day[best_day]) if best_day else None,
        worst_day=worst_day,
        worst_day_net=_optional(per_day[worst_day]) if worst_day else None,
        starting_balance=_optional(walk.starting_balance),
        ending_balance=_optional(walk.ending_balance),
    )
