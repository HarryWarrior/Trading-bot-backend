"""Shared test fakes and fixtures for every auth port."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from auth_service.application.use_cases.forgot_password import ForgotPassword
from auth_service.application.use_cases.refresh_session import RefreshSession
from auth_service.application.use_cases.resend_verification import ResendVerification
from auth_service.application.use_cases.reset_password import ResetPassword
from auth_service.application.use_cases.sign_in import SignIn
from auth_service.application.use_cases.sign_out import SignOut
from auth_service.application.use_cases.sign_up import SignUp
from auth_service.application.use_cases.verify_email import VerifyEmail
from auth_service.domain.user import Role, User


class FixedClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}

    async def add(self, user: User) -> None:
        self.users[user.id] = user

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email == email), None)

    async def get_by_id(self, user_id: str) -> User | None:
        return self.users.get(user_id)

    async def mark_verified(self, user_id: str) -> None:
        self.users[user_id] = replace(self.users[user_id], email_verified=True)

    async def set_password_hash(self, user_id: str, password_hash: str) -> None:
        self.users[user_id] = replace(self.users[user_id], password_hash=password_hash)

    async def set_role(self, user_id: str, role: Role) -> None:
        self.users[user_id] = replace(self.users[user_id], role=role)


class FakeVerificationRepository:
    def __init__(self) -> None:
        self.codes: dict[str, tuple[str, datetime]] = {}

    async def replace_code(self, email: str, code_hash: str, expires_at: datetime) -> None:
        self.codes[email] = (code_hash, expires_at)

    async def consume(self, email: str, code_hash: str, now: datetime) -> bool:
        entry = self.codes.get(email)
        if entry is None or entry[0] != code_hash or entry[1] <= now:
            return False
        del self.codes[email]
        return True


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[str, tuple[str, datetime]] = {}

    async def add(self, user_id: str, token_hash: str, expires_at: datetime) -> None:
        self.sessions[token_hash] = (user_id, expires_at)

    async def consume(self, token_hash: str, now: datetime) -> str | None:
        entry = self.sessions.pop(token_hash, None)
        if entry is None or entry[1] <= now:
            return None
        return entry[0]

    async def revoke(self, token_hash: str) -> None:
        self.sessions.pop(token_hash, None)

    async def revoke_all(self, user_id: str) -> None:
        self.sessions = {h: v for h, v in self.sessions.items() if v[0] != user_id}

    async def delete_expired(self, now: datetime) -> int:
        expired = [h for h, (_, exp) in self.sessions.items() if exp <= now]
        for token_hash in expired:
            del self.sessions[token_hash]
        return len(expired)


class FakePasswordResetRepository:
    def __init__(self) -> None:
        self.tokens: dict[str, tuple[str, datetime]] = {}

    async def add(self, user_id: str, token_hash: str, expires_at: datetime) -> None:
        self.tokens[token_hash] = (user_id, expires_at)

    async def consume(self, token_hash: str, now: datetime) -> str | None:
        entry = self.tokens.pop(token_hash, None)
        if entry is None or entry[1] <= now:
            return None
        return entry[0]


class FakePasswordHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"


class FakeAccessTokenIssuer:
    def issue(self, user: User) -> tuple[str, int]:
        return f"access-{user.id}", 900


class SequentialSecrets:
    def __init__(self) -> None:
        self.counter = 0

    def verification_code(self) -> str:
        self.counter += 1
        return f"{self.counter:06d}"

    def opaque_token(self) -> str:
        self.counter += 1
        return f"opaque-{self.counter}"


class RecordingEmailSender:
    def __init__(self) -> None:
        self.verifications: list[tuple[str, str]] = []
        self.resets: list[tuple[str, str]] = []

    async def send_verification(self, email: str, code: str) -> None:
        self.verifications.append((email, code))

    async def send_password_reset(self, email: str, token: str) -> None:
        self.resets.append((email, token))


class World:
    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.verifications = FakeVerificationRepository()
        self.sessions = FakeSessionRepository()
        self.resets = FakePasswordResetRepository()
        self.hasher = FakePasswordHasher()
        self.issuer = FakeAccessTokenIssuer()
        self.secrets = SequentialSecrets()
        self.email = RecordingEmailSender()
        self.clock = FixedClock()

    def sign_up(self):
        return SignUp(
            self.users, self.verifications, self.hasher, self.secrets, self.email, self.clock
        )

    def verify(self):
        return VerifyEmail(self.users, self.verifications, self.clock)

    def resend(self):
        return ResendVerification(
            self.users, self.verifications, self.secrets, self.email, self.clock
        )

    def sign_in(self):
        return SignIn(self.users, self.sessions, self.hasher, self.issuer, self.secrets, self.clock)

    def refresh(self):
        return RefreshSession(self.users, self.sessions, self.issuer, self.secrets, self.clock)

    def sign_out(self):
        return SignOut(self.sessions)

    def forgot(self):
        return ForgotPassword(self.users, self.resets, self.secrets, self.email, self.clock)

    def reset(self):
        return ResetPassword(self.users, self.resets, self.sessions, self.hasher, self.clock)

    async def registered_verified(self, email="user@mail.com", password="Secret123!"):
        user = await self.sign_up().execute(email, password, "Ana")
        await self.verify().execute(email, self.email.verifications[-1][1])
        return user


@pytest.fixture
def world() -> World:
    return World()
