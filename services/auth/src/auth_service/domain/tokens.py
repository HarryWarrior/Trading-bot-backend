"""Token value objects and hashing helpers. Secrets are only ever stored as digests."""

import hashlib
from dataclasses import dataclass
from datetime import timedelta

from auth_service.domain.user import User

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=7)
RESET_TOKEN_TTL = timedelta(hours=1)
VERIFICATION_CODE_TTL = timedelta(minutes=15)


def digest(value: str) -> str:
    """SHA-256 hex digest of a code or opaque token."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    user: User
