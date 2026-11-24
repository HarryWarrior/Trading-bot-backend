from datetime import datetime
from typing import Protocol

from mt5_service.domain.account import LinkedAccount, SyncResult


class LinkedAccountRepository(Protocol):
    """Every query is scoped by user_id; an account of another user is simply not found."""

    async def add(self, account: LinkedAccount) -> None:
        """Raises AccountAlreadyLinked if the account_ref is already linked (unique index)."""
        ...

    async def get(self, user_id: str, account_id: str) -> LinkedAccount | None: ...

    async def find_by_ref(self, account_ref: str) -> LinkedAccount | None:
        """Across ALL users: one terminal account can be linked to a single user."""
        ...

    async def list(self, user_id: str) -> list[LinkedAccount]: ...

    async def delete(self, user_id: str, account_id: str) -> bool: ...

    async def mark_synced(self, account_id: str, at: datetime, result: SyncResult) -> None: ...
