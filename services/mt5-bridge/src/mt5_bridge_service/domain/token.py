"""Ingest tokens: per-user, revocable secrets the EA uses to authenticate.

Only the SHA-256 hash of a token is ever kept; the plaintext exists once, when it is issued.
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime

from mt5_bridge_service.domain.errors import InvalidTokenName

INGEST_MT5_SCOPE = "ingest:mt5"
TOKEN_BYTES = 32
MAX_NAME_LENGTH = 100


def hash_token(plaintext: str) -> str:
    """Return the hex SHA-256 digest stored and looked up instead of the plaintext."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _require_aware(**values: datetime | None) -> None:
    for name, value in values.items():
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class IngestToken:
    id: str
    user_id: str
    name: str
    hash: str = field(repr=False)
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    scope: str = INGEST_MT5_SCOPE

    def __post_init__(self) -> None:
        _require_aware(
            created_at=self.created_at, last_used_at=self.last_used_at, revoked_at=self.revoked_at
        )

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @classmethod
    def issue(
        cls, token_id: str, user_id: str, name: str, at: datetime
    ) -> "tuple[IngestToken, str]":
        """Create a token and its plaintext (``TOKEN_BYTES`` random bytes, URL-safe base64).

        Raises:
            InvalidTokenName: If the stripped name is empty or longer than 100 characters.
        """
        clean_name = name.strip()
        if not clean_name or len(clean_name) > MAX_NAME_LENGTH:
            raise InvalidTokenName(f"Token name must be 1-{MAX_NAME_LENGTH} characters.")
        plaintext = secrets.token_urlsafe(TOKEN_BYTES)
        token = cls(
            id=token_id,
            user_id=user_id,
            name=clean_name,
            hash=hash_token(plaintext),
            created_at=at,
            last_used_at=None,
            revoked_at=None,
        )
        return token, plaintext
