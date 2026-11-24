"""Input of every KPI: closed trades (net result) and signed balance events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class TradeRecord:
    symbol: str
    side: str
    open_time: datetime
    close_time: datetime
    net: Decimal  # profit + commission + swap
    account_ref: str


@dataclass(frozen=True)
class BalanceRecord:
    time: datetime
    amount: Decimal  # signed: deposits > 0, withdrawals < 0, adjustments either way
    account_ref: str


@dataclass(frozen=True)
class Dataset:
    trades: list[TradeRecord] = field(default_factory=list)
    balance_events: list[BalanceRecord] = field(default_factory=list)

    def ordered_trades(self) -> list[TradeRecord]:
        return sorted(self.trades, key=lambda trade: trade.close_time)
