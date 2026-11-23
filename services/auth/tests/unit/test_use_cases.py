import importlib.util
from datetime import timedelta
from pathlib import Path

import pytest

from auth_service.application.use_cases.cleanup_expired_sessions import CleanupExpiredSessions
from auth_service.application.use_cases.forgot_password import ForgotPassword
from auth_service.application.use_cases.get_me import GetMe
from auth_service.application.use_cases.refresh_session import RefreshSession
from auth_service.application.use_cases.resend_verification import ResendVerification
from auth_service.application.use_cases.reset_password import ResetPassword
from auth_service.application.use_cases.sign_in import SignIn
from auth_service.application.use_cases.sign_out import SignOut
from auth_service.application.use_cases.sign_up import SignUp
from auth_service.application.use_cases.verify_email import VerifyEmail
from auth_service.domain.errors import (
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    InvalidToken,
    InvalidVerificationCode,
)
from auth_service.domain.tokens import digest
from auth_service.domain.user import Role, normalize_email


def _load_fakes():
    # Tests run in importlib mode (no package), so load the sibling module by path.
    path = Path(__file__).with_name("fakes.py")
    spec = importlib.util.spec_from_file_location("auth_service_unit_fakes", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fakes = _load_fakes()
FakeAccessTokenIssuer = fakes.FakeAccessTokenIssuer
FakePasswordHasher = fakes.FakePasswordHasher
FakePasswordResetRepository = fakes.FakePasswordResetRepository
FakeSessionRepository = fakes.FakeSessionRepository
FakeUserRepository = fakes.FakeUserRepository
FakeVerificationRepository = fakes.FakeVerificationRepository
FixedClock = fakes.FixedClock
RecordingEmailSender = fakes.RecordingEmailSender
SequentialSecrets = fakes.SequentialSecrets

pytestmark = pytest.mark.asyncio


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


async def test_sign_up_normalizes_email_and_sends_code():
    w = World()
    user = await w.sign_up().execute("  User@Mail.COM ", "Secret123!", "Ana")
    assert user.email == "user@mail.com"
    assert user.role == Role.USER
    assert user.email_verified is False
    assert len(w.email.verifications) == 1
    assert w.email.verifications[0][0] == "user@mail.com"
    stored_hash = w.verifications.codes["user@mail.com"][0]
    assert stored_hash == digest(w.email.verifications[0][1])


async def test_sign_up_duplicate_any_casing_raises_email_already_registered():
    w = World()
    await w.sign_up().execute("user@mail.com", "Secret123!", "Ana")
    with pytest.raises(EmailAlreadyRegistered) as exc:
        await w.sign_up().execute("  USER@Mail.com", "Other123!", "Bob")
    assert exc.value.code == "EMAIL_ALREADY_REGISTERED"
    assert exc.value.http_status == 409


async def test_sign_up_then_sign_in_with_other_casing_is_same_account():
    w = World()
    user = await w.sign_up().execute("  User@Mail.COM ", "Secret123!", "Ana")
    await w.verify().execute("user@mail.com", w.email.verifications[-1][1])
    tokens = await w.sign_in().execute("USER@mail.com", "Secret123!")
    assert tokens.user.id == user.id


async def test_sign_in_before_verification_raises_email_not_verified():
    w = World()
    await w.sign_up().execute("user@mail.com", "Secret123!", "Ana")
    with pytest.raises(EmailNotVerified) as exc:
        await w.sign_in().execute("user@mail.com", "Secret123!")
    assert exc.value.code == "EMAIL_NOT_VERIFIED"
    assert exc.value.http_status == 403


async def test_verify_with_wrong_code_raises():
    w = World()
    await w.sign_up().execute("user@mail.com", "Secret123!", "Ana")
    with pytest.raises(InvalidVerificationCode) as exc:
        await w.verify().execute("user@mail.com", "000000")
    assert exc.value.code == "INVALID_VERIFICATION_CODE"
    assert exc.value.http_status == 400


async def test_verify_marks_user_verified():
    w = World()
    user = await w.registered_verified()
    assert w.users.users[user.id].email_verified is True


async def test_verify_code_expires_after_15_minutes():
    w = World()
    await w.sign_up().execute("user@mail.com", "Secret123!", "Ana")
    code = w.email.verifications[-1][1]
    w.clock.advance(timedelta(minutes=15, seconds=1))
    with pytest.raises(InvalidVerificationCode):
        await w.verify().execute("user@mail.com", code)


async def test_verify_code_is_single_use():
    w = World()
    await w.sign_up().execute("user@mail.com", "Secret123!", "Ana")
    code = w.email.verifications[-1][1]
    await w.verify().execute("user@mail.com", code)
    with pytest.raises(InvalidVerificationCode):
        await w.verify().execute("user@mail.com", code)


async def test_resend_verification_replaces_code_and_unknown_email_is_silent():
    w = World()
    await w.sign_up().execute("user@mail.com", "Secret123!", "Ana")
    first = w.email.verifications[-1][1]
    await w.resend().execute(" USER@mail.com")
    second = w.email.verifications[-1][1]
    assert len(w.email.verifications) == 2
    with pytest.raises(InvalidVerificationCode):
        await w.verify().execute("user@mail.com", first)
    await w.verify().execute("user@mail.com", second)
    await w.resend().execute("ghost@mail.com")
    await w.resend().execute("user@mail.com")  # already verified: nothing sent
    assert len(w.email.verifications) == 2


async def test_sign_in_wrong_password_raises_invalid_credentials():
    w = World()
    await w.registered_verified()
    with pytest.raises(InvalidCredentials) as exc:
        await w.sign_in().execute("user@mail.com", "wrong")
    assert exc.value.code == "INVALID_CREDENTIALS"
    assert exc.value.http_status == 401


async def test_sign_in_unknown_email_raises_invalid_credentials():
    w = World()
    with pytest.raises(InvalidCredentials):
        await w.sign_in().execute("ghost@mail.com", "whatever")


async def test_sign_in_returns_access_and_refresh_tokens():
    w = World()
    user = await w.registered_verified()
    tokens = await w.sign_in().execute("user@mail.com", "Secret123!")
    assert tokens.access_token == f"access-{user.id}"
    assert tokens.expires_in == 900
    assert tokens.refresh_token
    assert digest(tokens.refresh_token) in w.sessions.sessions
    assert tokens.refresh_token not in w.sessions.sessions
    _, expires_at = w.sessions.sessions[digest(tokens.refresh_token)]
    assert expires_at == w.clock.now() + timedelta(days=7)


async def test_refresh_rotates_token_and_old_one_is_rejected():
    w = World()
    await w.registered_verified()
    first = await w.sign_in().execute("user@mail.com", "Secret123!")
    second = await w.refresh().execute(first.refresh_token)
    assert second.refresh_token != first.refresh_token
    assert second.user.id == first.user.id
    with pytest.raises(InvalidToken) as exc:
        await w.refresh().execute(first.refresh_token)
    assert exc.value.code == "INVALID_TOKEN"
    assert exc.value.http_status == 401
    await w.refresh().execute(second.refresh_token)


async def test_refresh_with_expired_token_raises():
    w = World()
    await w.registered_verified()
    tokens = await w.sign_in().execute("user@mail.com", "Secret123!")
    w.clock.advance(timedelta(days=7, seconds=1))
    with pytest.raises(InvalidToken):
        await w.refresh().execute(tokens.refresh_token)


async def test_sign_out_revokes_refresh_token():
    w = World()
    await w.registered_verified()
    tokens = await w.sign_in().execute("user@mail.com", "Secret123!")
    await w.sign_out().execute(tokens.refresh_token)
    with pytest.raises(InvalidToken):
        await w.refresh().execute(tokens.refresh_token)


async def test_forgot_password_unknown_email_sends_nothing_and_does_not_raise():
    w = World()
    await w.forgot().execute("ghost@mail.com")
    assert w.email.resets == []
    assert w.resets.tokens == {}


async def test_forgot_password_known_email_sends_token_stored_hashed():
    w = World()
    await w.registered_verified()
    await w.forgot().execute(" User@Mail.com")
    email, token = w.email.resets[0]
    assert email == "user@mail.com"
    assert digest(token) in w.resets.tokens
    assert token not in w.resets.tokens


async def test_reset_password_changes_hash_revokes_all_sessions_and_is_single_use():
    w = World()
    user = await w.registered_verified()
    t1 = await w.sign_in().execute("user@mail.com", "Secret123!")
    t2 = await w.sign_in().execute("user@mail.com", "Secret123!")
    await w.forgot().execute("user@mail.com")
    token = w.email.resets[-1][1]
    await w.reset().execute(token, "NewSecret456!")
    assert w.users.users[user.id].password_hash == w.hasher.hash("NewSecret456!")
    for old in (t1, t2):
        with pytest.raises(InvalidToken):
            await w.refresh().execute(old.refresh_token)
    with pytest.raises(InvalidToken):
        await w.reset().execute(token, "Another789!")
    await w.sign_in().execute("user@mail.com", "NewSecret456!")


async def test_reset_token_expires_after_1_hour():
    w = World()
    await w.registered_verified()
    await w.forgot().execute("user@mail.com")
    token = w.email.resets[-1][1]
    w.clock.advance(timedelta(hours=1, seconds=1))
    with pytest.raises(InvalidToken):
        await w.reset().execute(token, "NewSecret456!")


async def test_get_me_returns_user_or_invalid_token():
    w = World()
    user = await w.registered_verified()
    me = await GetMe(w.users).execute(user.id)
    assert me.email == "user@mail.com"
    with pytest.raises(InvalidToken):
        await GetMe(w.users).execute("missing")


async def test_cleanup_deletes_only_expired_sessions():
    w = World()
    await w.registered_verified()
    await w.sign_in().execute("user@mail.com", "Secret123!")
    w.clock.advance(timedelta(days=6))
    await w.sign_in().execute("user@mail.com", "Secret123!")
    w.clock.advance(timedelta(days=1, seconds=1))
    deleted = await CleanupExpiredSessions(w.sessions, w.clock).execute()
    assert deleted == 1
    assert len(w.sessions.sessions) == 1


async def test_normalize_email_strips_and_lowercases():
    assert normalize_email("  A@B.Com ") == "a@b.com"
