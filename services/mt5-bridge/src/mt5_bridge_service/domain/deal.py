"""Raw MT5 deal as the EA pushes it (times in UTC). Forwarded untouched to journal, which pairs it.

A small copy of journal's DTO on purpose: services never share domain models.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class RawDeal:
    ticket: int
    position_id: int
    time: datetime  # UTC, tz-aware
    type: int  # MT5 DEAL_TYPE_*
    entry: int  # MT5 DEAL_ENTRY_*
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
        if self.time.tzinfo is None or self.time.utcoffset() is None:
            raise ValueError("time must be timezone-aware")
