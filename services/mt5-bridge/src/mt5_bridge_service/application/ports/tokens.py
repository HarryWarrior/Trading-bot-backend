from datetime import datetime
from typing import Protocol

from mt5_bridge_service.domain.token import IngestToken


class TokenRepository(Protocol):
    """Ingest token store. Every method filters by ``user_id`` except ``find_active_by_hash``,
    which is how the owner of an EA request is found in the first place."""

    async def add(self, token: IngestToken) -> None: ...

    async def get(self, user_id: str, token_id: str) -> IngestToken | None: ...

    async def list_for_user(self, user_id: str) -> list[IngestToken]:
        """Newest first."""
        ...

    async def mark_revoked(self, user_id: str, token_id: str, at: datetime) -> None:
        """Set ``revoked_at`` once; revoking again keeps the first time."""
        ...

    async def find_active_by_hash(self, token_hash: str) -> IngestToken | None: ...

    async def touch_last_used(self, user_id: str, token_id: str, at: datetime) -> None: ...
