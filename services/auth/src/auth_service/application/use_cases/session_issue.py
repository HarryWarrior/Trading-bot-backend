"""Shared helper: open a session and build the token pair."""

from datetime import timedelta

from auth_service.application.ports.clock import Clock
from auth_service.application.ports.repositories import SessionRepository
from auth_service.application.ports.security import AccessTokenIssuer, SecretGenerator
from auth_service.domain.tokens import REFRESH_TOKEN_TTL, AuthTokens, digest
from auth_service.domain.user import User


async def open_session(
    user: User,
    sessions: SessionRepository,
    issuer: AccessTokenIssuer,
    secrets: SecretGenerator,
    clock: Clock,
    refresh_ttl: timedelta = REFRESH_TOKEN_TTL,
) -> AuthTokens:
    access_token, expires_in = issuer.issue(user)
    refresh_token = secrets.opaque_token()
    await sessions.add(user.id, digest(refresh_token), clock.now() + refresh_ttl)
    return AuthTokens(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in, user=user
    )
