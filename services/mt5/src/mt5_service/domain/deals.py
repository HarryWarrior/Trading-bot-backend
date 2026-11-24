from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import IntEnum


class DealType(IntEnum):
    """MetaTrader5 DEAL_TYPE_* values."""

    BUY = 0
    SELL = 1
    BALANCE = 2
    CREDIT = 3
    CHARGE = 4
    CORRECTION = 5
    BONUS = 6
    COMMISSION = 7
    COMMISSION_DAILY = 8
    COMMISSION_MONTHLY = 9
    COMMISSION_AGENT_DAILY = 10
    COMMISSION_AGENT_MONTHLY = 11
    INTEREST = 12
    BUY_CANCELED = 13
    SELL_CANCELED = 14
    DIVIDEND = 15
    DIVIDEND_FRANKED = 16
    TAX = 17


class DealEntry(IntEnum):
    """MetaTrader5 DEAL_ENTRY_* values."""

    IN = 0
    OUT = 1
    INOUT = 2
    OUT_BY = 3


@dataclass(frozen=True)
class Deal:
    ticket: int
    position_id: int
    time_server: datetime  # naive broker server time
    type: DealType | int  # raw int when the broker reports a value outside the enum
    entry: DealEntry | int
    symbol: str
    volume: Decimal
    price: Decimal
    commission: Decimal
    swap: Decimal
    fee: Decimal
    profit: Decimal
    comment: str

    def __post_init__(self) -> None:
        if self.time_server.tzinfo is not None:
            raise ValueError("time_server must be naive (broker server time)")


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    tick_volume: int
