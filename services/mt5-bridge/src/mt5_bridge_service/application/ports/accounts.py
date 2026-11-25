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
