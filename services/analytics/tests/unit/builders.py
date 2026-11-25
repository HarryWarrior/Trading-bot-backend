"""Test builders for trades and balance events."""

from datetime import UTC, datetime
from decimal import Decimal

from analytics_service.domain.dataset import BalanceRecord, TradeRecord


def utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def make_trade(
    close: str, net: str, symbol: str = "EURUSD", side: str = "BUY", account: str = "A"
) -> TradeRecord:
    closed = utc(close)
    return TradeRecord(
        symbol=symbol,
        side=side,
        open_time=closed,
        close_time=closed,
        net=Decimal(net),
        account_ref=account,
    )


def make_balance(time: str, amount: str, account: str = "A") -> BalanceRecord:
    return BalanceRecord(time=utc(time), amount=Decimal(amount), account_ref=account)
