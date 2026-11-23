"""Shared helper: open a session and build the token pair."""

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
) -> AuthTokens:
    access_token, expires_in = issuer.issue(user)
    refresh_token = secrets.opaque_token()
    await sessions.add(user.id, digest(refresh_token), clock.now() + REFRESH_TOKEN_TTL)
    return AuthTokens(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in, user=user
    )
