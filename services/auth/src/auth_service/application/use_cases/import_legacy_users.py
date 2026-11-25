import re
from dataclasses import dataclass
from datetime import UTC, datetime

from auth_service.application.ports.legacy_users import LegacyUser, LegacyUserSource
from auth_service.application.ports.repositories import UserRepository
from auth_service.domain.errors import EmailAlreadyRegistered
from auth_service.domain.user import Role, User, normalize_email

_BCRYPT_HASH = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")


@dataclass(frozen=True)
class ImportReport:
    imported: int
    skipped_existing: int
    skipped_invalid: int


class ImportLegacyUsers:
    """Copy legacy users into the auth store, keeping their bcrypt hashes (idempotent)."""

    def __init__(self, source: LegacyUserSource, users: UserRepository) -> None:
        self._source = source
        self._users = users

    async def execute(self) -> ImportReport:
        imported = skipped_existing = skipped_invalid = 0
        for legacy in await self._source.list_users():
            user = self._to_user(legacy)
            if user is None:
                skipped_invalid += 1
                continue
            if await self._users.get_by_email(user.email) is not None:
                skipped_existing += 1
                continue
            try:
                await self._users.add(user)
            except EmailAlreadyRegistered:
                skipped_existing += 1
                continue
            imported += 1
        return ImportReport(imported, skipped_existing, skipped_invalid)

    @staticmethod
    def _to_user(legacy: LegacyUser) -> User | None:
        email = normalize_email(legacy.email) if isinstance(legacy.email, str) else ""
        password_hash = legacy.password_hash
        if not email or not isinstance(password_hash, str) or not _BCRYPT_HASH.match(password_hash):
            return None
        try:
            role = Role(legacy.role)
        except ValueError:
            role = Role.USER
        created_at = legacy.created_at or datetime.now(UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return User(
            id=legacy.id,
            email=email,
            name=(legacy.name or "").strip(),
            role=role,
            password_hash=password_hash,
            email_verified=legacy.email_verified is True,
            created_at=created_at,
        )
