"""Time series and breakdowns. Days, months and hours are UTC, taken from close_time."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal
from typing import Any

from analytics_service.domain.dataset import Dataset, TradeRecord
from analytics_service.domain.equity import ZERO, EquityPoint, walk_equity
from analytics_service.domain.rounding import round_money

HUNDRED = Decimal(100)


@dataclass(frozen=True)
class DailyStat:
    day: date
    trades: int
    net: Decimal


@dataclass(frozen=True)
class MonthlyStat:
    month: str  # "YYYY-MM"
    trades: int
    net: Decimal


@dataclass(frozen=True)
class SymbolStat:
    symbol: str
    trades: int
    wins: int
    win_rate: Decimal
    net: Decimal


@dataclass(frozen=True)
class HourStat:
    hour: int  # 0-23 UTC
    trades: int
    net: Decimal


def equity_curve(dataset: Dataset) -> list[EquityPoint]:
    """One point per trade (at close_time) and per balance event after the starting balance.

    Balance events up to the first trade are the base of the first point (0 when there are none).
    """
    return walk_equity(dataset).points


def _group(dataset: Dataset, key: Callable[[TradeRecord], Any]) -> dict[Any, list[Decimal]]:
    groups: dict[Any, list[Decimal]] = {}
    for trade in dataset.ordered_trades():
        groups.setdefault(key(trade), []).append(trade.net)
    return groups


def daily(dataset: Dataset) -> list[DailyStat]:
    groups = _group(dataset, lambda t: t.close_time.astimezone(UTC).date())
    return [DailyStat(k, len(v), round_money(sum(v, ZERO))) for k, v in sorted(groups.items())]


def monthly(dataset: Dataset) -> list[MonthlyStat]:
    groups = _group(dataset, lambda t: t.close_time.astimezone(UTC).strftime("%Y-%m"))
    return [MonthlyStat(k, len(v), round_money(sum(v, ZERO))) for k, v in sorted(groups.items())]


def hourly(dataset: Dataset) -> list[HourStat]:
    groups = _group(dataset, lambda t: t.close_time.astimezone(UTC).hour)
    return [HourStat(k, len(v), round_money(sum(v, ZERO))) for k, v in sorted(groups.items())]


def by_symbol(dataset: Dataset) -> list[SymbolStat]:
    """Ordered by net descending, then symbol."""
    rows = []
    for symbol, nets in _group(dataset, lambda t: t.symbol).items():
        wins = sum(1 for n in nets if n > 0)
        rows.append(
            SymbolStat(
                symbol=symbol,
                trades=len(nets),
                wins=wins,
                win_rate=round_money(Decimal(wins) / len(nets) * HUNDRED),
                net=round_money(sum(nets, ZERO)),
            )
        )
    return sorted(rows, key=lambda r: (-r.net, r.symbol))
