"""Raw MT5 deals as pushed by the EA bridge (times already in UTC)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import IntEnum

from journal_service.domain.trade import require_aware


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
class RawDeal:
    """One MT5 deal. ``type`` and ``entry`` stay raw ints so unknown broker values survive."""

    ticket: int
    position_id: int
    time: datetime  # UTC, tz-aware
    type: int
    entry: int
    symbol: str
    volume: Decimal
    price: Decimal
    commission: Decimal
    swap: Decimal
    profit: Decimal
    sl: Decimal | None
    tp: Decimal | None
    comment: str | None
    fee: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        require_aware(time=self.time)
