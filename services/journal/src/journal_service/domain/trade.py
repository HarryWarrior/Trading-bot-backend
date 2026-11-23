from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class Outcome(StrEnum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"


def require_aware(**values: datetime) -> None:
    for name, value in values.items():
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class Trade:
    id: str
    user_id: str
    account_ref: str
    position_id: str | None
    row_hash: str | None
    source: Literal["report", "mt5"]
    import_id: str | None
    symbol: str
    side: Side
    volume: Decimal
    open_time: datetime
    close_time: datetime
    open_price: Decimal
    close_price: Decimal
    stop_loss: Decimal | None
    take_profit: Decimal | None
    commission: Decimal
    swap: Decimal
    profit: Decimal
    comment: str | None

    def __post_init__(self) -> None:
        require_aware(open_time=self.open_time, close_time=self.close_time)

    @property
    def net(self) -> Decimal:
        return self.profit + self.commission + self.swap

    @property
    def outcome(self) -> Outcome:
        net = self.net
        if net > 0:
            return Outcome.WIN
        if net < 0:
            return Outcome.LOSS
        return Outcome.BREAKEVEN

    @property
    def duration_minutes(self) -> int:
        return int((self.close_time - self.open_time).total_seconds() // 60)
