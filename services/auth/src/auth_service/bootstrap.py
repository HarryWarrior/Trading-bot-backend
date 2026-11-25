"""Composition root: the only place that knows which adapter implements which port."""

import logging
from dataclasses import dataclass
from datetime import timedelta

from motor.motor_asyncio import AsyncIOMotorClient

from auth_service.adapters.outbound.bcrypt_hasher import BcryptPasswordHasher
from auth_service.adapters.outbound.email_senders import LogEmailSender, SmtpEmailSender
from auth_service.adapters.outbound.jwt_issuer import JwtAccessTokenIssuer
from auth_service.adapters.outbound.mongo_repositories import (
    MongoPasswordResetRepository,
    MongoSessionRepository,
    MongoUserRepository,
    MongoVerificationRepository,
)
from auth_service.adapters.outbound.secrets_generator import SecretsGenerator
from auth_service.adapters.outbound.system_clock import SystemClock
from auth_service.application.ports.email import EmailSender
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
from auth_service.settings import AuthSettings
from trading_shared.mongo import create_mongo_client

logger = logging.getLogger("auth_service.email")


@dataclass(frozen=True)
class Container:
    settings: AuthSettings
    mongo_client: AsyncIOMotorClient
    repositories: tuple
    sign_up: SignUp
    verify_email: VerifyEmail
    resend_verification: ResendVerification
    sign_in: SignIn
    refresh_session: RefreshSession
    sign_out: SignOut
    forgot_password: ForgotPassword
    reset_password: ResetPassword
    get_me: GetMe
    cleanup_expired_sessions: CleanupExpiredSessions

    async def create_indexes(self) -> None:
        for repository in self.repositories:
            await repository.create_indexes()

    def close(self) -> None:
        self.mongo_client.close()


def _default_email_sender(settings: AuthSettings) -> EmailSender:
    if settings.smtp_host:
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user or "",
            password=settings.smtp_password.get_secret_value() if settings.smtp_password else "",
            from_email=settings.smtp_from_email or "",
            frontend_url=settings.frontend_url,
        )
    if settings.environment != "local":
        raise ValueError(
            f"SMTP_HOST is required when ENVIRONMENT={settings.environment}; "
            "emails are only logged when ENVIRONMENT=local"
        )
    return LogEmailSender(logger, settings.frontend_url)


def build_container(settings: AuthSettings, email_sender: EmailSender | None = None) -> Container:
    client = create_mongo_client(settings.mongodb_url)
    db = client[settings.database_name]
    users = MongoUserRepository(db)
    verifications = MongoVerificationRepository(db)
    sessions = MongoSessionRepository(db)
    resets = MongoPasswordResetRepository(db)
    hasher = BcryptPasswordHasher()
    issuer = JwtAccessTokenIssuer(
        settings.jwt_secret_key.get_secret_value(), settings.access_token_minutes
    )
    secrets = SecretsGenerator()
    clock = SystemClock()
    refresh_ttl = timedelta(days=settings.refresh_token_days)
    sender = email_sender or _default_email_sender(settings)
    return Container(
        settings=settings,
        mongo_client=client,
        repositories=(users, verifications, sessions, resets),
        sign_up=SignUp(users, verifications, hasher, secrets, sender, clock),
        verify_email=VerifyEmail(users, verifications, clock),
        resend_verification=ResendVerification(users, verifications, secrets, sender, clock),
        sign_in=SignIn(users, sessions, hasher, issuer, secrets, clock, refresh_ttl),
        refresh_session=RefreshSession(users, sessions, issuer, secrets, clock, refresh_ttl),
        sign_out=SignOut(sessions),
        forgot_password=ForgotPassword(users, resets, secrets, sender, clock),
        reset_password=ResetPassword(users, resets, sessions, hasher, clock),
        get_me=GetMe(users),
        cleanup_expired_sessions=CleanupExpiredSessions(sessions, clock),
    )
