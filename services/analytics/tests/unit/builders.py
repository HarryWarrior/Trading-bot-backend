"""Test builders for trades and balance events."""

from datetime import UTC, datetime
from decimal import Decimal

from analytics_service.domain.dataset import BalanceRecord, TradeRecord


def utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def make_trade(close: str, net: str, symbol: str = "EURUSD", side: str = "BUY") -> TradeRecord:
    closed = utc(close)
    return TradeRecord(symbol, side, closed, closed, Decimal(net))


def make_balance(time: str, amount: str) -> BalanceRecord:
    return BalanceRecord(utc(time), Decimal(amount))
