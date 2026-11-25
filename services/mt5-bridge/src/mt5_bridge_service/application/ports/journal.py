from dataclasses import dataclass
from typing import Protocol

from mt5_bridge_service.domain.deal import RawDeal


@dataclass(frozen=True)
class IngestDealsResult:
    """What journal reports back for one forwarded batch."""

    received: int
    new: int
    trades_upserted: int


class JournalGateway(Protocol):
    """Forwards raw deals to the journal service (implemented in an outbound HTTP adapter)."""

    async def ingest_deals(
        self, user_id: str, account_ref: str, deals: list[RawDeal]
    ) -> IngestDealsResult:
        """Raises JournalUnavailable (retryable) or JournalRejected (never retryable)."""
        ...
