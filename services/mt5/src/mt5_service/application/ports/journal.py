from dataclasses import dataclass
from typing import Protocol

from mt5_service.domain.trades import BalanceEventOut, TradeOut


@dataclass(frozen=True)
class IngestResult:
    created: int
    updated: int
    balance_events: int


class JournalGateway(Protocol):
    async def ingest(
        self,
        token: str,
        account_ref: str,
        trades: list[TradeOut],
        balance_events: list[BalanceEventOut],
    ) -> IngestResult:
        """Raises JournalUnavailable."""
        ...
