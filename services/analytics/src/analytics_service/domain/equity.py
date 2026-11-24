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


def _every_traded_account_is_funded(dataset: Dataset) -> bool:
    """True when each account with trades has a balance event at or before its first trade."""
    first_close: dict[str, datetime] = {}
    for trade in dataset.trades:
        known = first_close.get(trade.account_ref)
        if known is None or trade.close_time < known:
            first_close[trade.account_ref] = trade.close_time
    funded = {
        account
        for account, first in first_close.items()
        if any(b.account_ref == account and b.time <= first for b in dataset.balance_events)
    }
    return funded == set(first_close)


def walk_equity(dataset: Dataset) -> EquityWalk:
    """Walk events of every account in scope in one time-ordered pass.

    Equity is additive, so the merged walk equals the sum of the per-account walks. Balance
    events go before trades on equal timestamps. Balance events up to the first trade's close
    time (all of them when there are no trades) form the base of the walk; later ones shift
    equity and the running peak by the same amount, so deposits, withdrawals and adjustments
    never count as drawdown; only trade results do.

    The starting (and ending) balance is known only when every account that has trades has
    balance events at or before its own first trade; otherwise it is None, because balance
    data of another account must not become the base of unfunded trades. In that case the walk
    starts at 0 and every balance event, early ones included, is a point of the walk.
    """
    trades = dataset.ordered_trades()
    balances = sorted(dataset.balance_events, key=lambda event: event.time)
    first_close = trades[0].close_time if trades else None

    initial = [b for b in balances if first_close is None or b.time <= first_close]
    known = bool(initial) and _every_traded_account_is_funded(dataset)
    if not known:
        # No base is assumed: the walk starts at 0 and every balance event is a point.
        initial = []
    later = balances[len(initial) :]
    base = sum((b.amount for b in initial), ZERO)

    # (time, kind, amount): kind 0 = balance, 1 = trade -> balance first on ties.
    events = [(b.time, 0, b.amount) for b in later] + [(t.close_time, 1, t.net) for t in trades]
    events.sort(key=lambda event: (event[0], event[1]))

    equity = base
    peak = equity
    worst = ZERO
    worst_peak = peak
    points: list[EquityPoint] = []
    for time, kind, amount in events:
        equity += amount
        if kind == 0:
            peak += amount
        peak = max(peak, equity)
        points.append(EquityPoint(time, equity))
        drawdown = equity - peak
        if drawdown < worst:
            worst = drawdown
            worst_peak = peak
    return EquityWalk(
        starting_balance=base if known else None,
        ending_balance=equity if known else None,
        points=points,
        max_drawdown=worst,
        max_drawdown_peak=worst_peak,
    )
