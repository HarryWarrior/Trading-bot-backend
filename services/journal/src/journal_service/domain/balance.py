from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from journal_service.domain.trade import require_aware


@dataclass(frozen=True)
class BalanceEvent:
    id: str
    user_id: str
    account_ref: str
    kind: Literal["deposit", "withdrawal", "credit"]
    amount: Decimal  # signed: withdrawals are negative
    time: datetime
    source_ref: str
    comment: str | None

    def __post_init__(self) -> None:
        require_aware(time=self.time)
