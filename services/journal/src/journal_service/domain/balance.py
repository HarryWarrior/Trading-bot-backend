from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from journal_service.domain.trade import require_aware

# adjustment: broker-side corrections, charges, bonuses, commissions, interest, dividends,
# taxes... (MT5 Deals rows that are neither trades nor balance/credit), signed.
BalanceKind = Literal["deposit", "withdrawal", "credit", "adjustment"]


@dataclass(frozen=True)
class BalanceEvent:
    id: str
    user_id: str
    account_ref: str
    kind: BalanceKind
    amount: Decimal  # signed: withdrawals are negative, adjustments either way
    time: datetime
    source_ref: str
    comment: str | None

    def __post_init__(self) -> None:
        require_aware(time=self.time)
