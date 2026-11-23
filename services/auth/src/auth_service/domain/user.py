"""User entity and email normalization."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    USER = "user"
    TRADER = "trader"
    ADMIN = "admin"


def normalize_email(raw: str) -> str:
    """Return the canonical form of an email: stripped and lower-cased."""
    return raw.strip().lower()


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str
    role: Role
    password_hash: str
    email_verified: bool
    created_at: datetime
