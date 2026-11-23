import logging
from datetime import UTC, datetime

import pytest

from auth_service.adapters.outbound.bcrypt_hasher import BcryptPasswordHasher
from auth_service.adapters.outbound.email_senders import LogEmailSender, SmtpEmailSender
from auth_service.adapters.outbound.jwt_issuer import JwtAccessTokenIssuer
from auth_service.adapters.outbound.secrets_generator import SecretsGenerator
from auth_service.adapters.outbound.system_clock import SystemClock
from auth_service.domain.user import Role, User
from trading_shared.auth import CurrentUser, decode_access_token

SECRET = "unit-test-secret-with-enough-length-0123456789"


def _user() -> User:
    return User(
        id="u1",
        email="user@mail.com",
        name="Ana",
        role=Role.TRADER,
        password_hash="x",
        email_verified=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_bcrypt_verifies_and_rejects():
    hasher = BcryptPasswordHasher(rounds=4)
    hashed = hasher.hash("Secret123!")
    assert hashed != "Secret123!"
    assert hasher.verify("Secret123!", hashed) is True
    assert hasher.verify("wrong", hashed) is False
    assert hasher.verify("Secret123!", "not-a-hash") is False


def test_jwt_round_trips_through_shared_decoder():
    token, expires_in = JwtAccessTokenIssuer(SECRET, minutes=15).issue(_user())
    assert expires_in == 900
    assert decode_access_token(token, SECRET) == CurrentUser(
        id="u1", email="user@mail.com", role="trader"
    )


def test_verification_code_is_six_digits_and_tokens_are_unique():
    secrets_gen = SecretsGenerator()
    for _ in range(50):
        code = secrets_gen.verification_code()
        assert len(code) == 6 and code.isdigit()
    assert secrets_gen.opaque_token() != secrets_gen.opaque_token()
    assert len(secrets_gen.opaque_token()) >= 40


def test_system_clock_is_timezone_aware_utc():
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 0


@pytest.mark.asyncio
async def test_log_email_sender_writes_code_and_reset_link(caplog):
    logger = logging.getLogger("auth.test.email")
    sender = LogEmailSender(logger)
    with caplog.at_level(logging.INFO, logger="auth.test.email"):
        await sender.send_verification("user@mail.com", "123456")
        await sender.send_password_reset("user@mail.com", "tok")
    assert "verification code for user@mail.com: 123456" in caplog.text
    assert "tok" in caplog.text


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.calls: list[str] = []
        self.message = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(f"login:{user}:{password}")

    def send_message(self, message):
        self.calls.append("send")
        self.message = message


@pytest.mark.asyncio
async def test_smtp_sender_uses_starttls_login_and_sends():
    FakeSMTP.instances.clear()
    sender = SmtpEmailSender(
        "smtp.test", 587, "bot", "pw", "noreply@test", "https://app.test", smtp_factory=FakeSMTP
    )
    await sender.send_verification("user@mail.com", "123456")
    await sender.send_password_reset("user@mail.com", "tok")
    first, second = FakeSMTP.instances
    assert (first.host, first.port) == ("smtp.test", 587)
    assert first.calls == ["starttls", "login:bot:pw", "send"]
    assert first.message["To"] == "user@mail.com"
    assert first.message["From"] == "noreply@test"
    assert "123456" in first.message.get_content()
    assert "https://app.test" in second.message.get_content()
    assert "tok" in second.message.get_content()
