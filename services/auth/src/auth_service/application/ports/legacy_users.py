from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class LegacyUser:
    """A user as stored by the legacy app; any field may be missing or malformed."""

    id: str
    email: str | None
    password_hash: str | None
    name: str | None
    role: str | None
    email_verified: bool | None
    created_at: datetime | None


class LegacyUserSource(Protocol):
    async def list_users(self) -> list[LegacyUser]: ...
