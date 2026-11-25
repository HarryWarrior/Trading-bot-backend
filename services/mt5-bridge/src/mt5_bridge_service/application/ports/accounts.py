from datetime import datetime
from typing import Protocol

from mt5_bridge_service.domain.account import BrokerAccount


class AccountRepository(Protocol):
    async def upsert_heartbeat(self, account: BrokerAccount) -> BrokerAccount:
        """Upsert by ``(user_id, account_ref)`` and return the stored account.

        Heartbeat fields are overwritten; ``last_deal_at`` is kept as stored.
        """
        ...

    async def list_for_user(self, user_id: str) -> list[BrokerAccount]:
        """Ordered by ``account_ref``."""
        ...

    async def touch_last_deal(self, user_id: str, account_ref: str, at: datetime) -> None:
        """Raise ``last_deal_at`` to ``at`` (never lowers it).

        No-op when the user has no such account yet: accounts are created by heartbeats.
        """
        ...
