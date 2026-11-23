"""Equity walk shared by the summary (drawdown) and the equity curve."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from analytics_service.domain.dataset import Dataset

ZERO = Decimal(0)


@dataclass(frozen=True)
class EquityPoint:
    time: datetime
    equity: Decimal


@dataclass(frozen=True)
class EquityWalk:
    starting_balance: Decimal | None
    ending_balance: Decimal | None
    points: list[EquityPoint]
    max_drawdown: Decimal  # <= 0
    max_drawdown_peak: Decimal  # running peak at the worst point


def walk_equity(dataset: Dataset) -> EquityWalk:
    """Walk events in time order (balance before trade on equal timestamps).

    Balance events up to the first trade's close time form the starting balance; with no trades
    every balance event does. Without any starting balance the equity starts at 0, but the
    starting balance stays unknown (None).
    """
    trades = dataset.ordered_trades()
    balances = sorted(dataset.balance_events, key=lambda event: event.time)
    first_close = trades[0].close_time if trades else None

    initial = [b for b in balances if first_close is None or b.time <= first_close]
    later = balances[len(initial) :]
    starting = sum((b.amount for b in initial), ZERO) if initial else None

    # (time, kind, amount): kind 0 = balance, 1 = trade -> balance first on ties.
    events = [(b.time, 0, b.amount) for b in later] + [(t.close_time, 1, t.net) for t in trades]
    events.sort(key=lambda event: (event[0], event[1]))

    equity = starting if starting is not None else ZERO
    peak = equity
    worst = ZERO
    worst_peak = peak
    points: list[EquityPoint] = []
    for time, _kind, amount in events:
        equity += amount
        peak = max(peak, equity)
        points.append(EquityPoint(time, equity))
        drawdown = equity - peak
        if drawdown < worst:
            worst = drawdown
            worst_peak = peak
    return EquityWalk(
        starting_balance=starting,
        ending_balance=equity if starting is not None else None,
        points=points,
        max_drawdown=worst,
        max_drawdown_peak=worst_peak,
    )
