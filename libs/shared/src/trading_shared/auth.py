"""Local JWT verification for services. Inbound adapters only (FastAPI)."""

from collections.abc import Callable
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header

from trading_shared.errors import AppError

ALGORITHM = "HS256"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    role: str


def _unauthenticated(message: str = "Authentication required") -> AppError:
    return AppError("UNAUTHENTICATED", message, 401)


def decode_access_token(token: str, secret: str) -> CurrentUser:
    """Verify an HS256 access token and return the user it identifies."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthenticated("Access token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthenticated("Invalid access token") from exc
    sub, email, role = claims.get("sub"), claims.get("email"), claims.get("role")
    if not all(isinstance(value, str) and value for value in (sub, email, role)):
        raise _unauthenticated("Invalid access token")
    return CurrentUser(id=sub, email=email, role=role)


def current_user_dependency(get_secret: Callable[[], str]) -> Callable[..., CurrentUser]:
    """Build a FastAPI dependency that reads ``Authorization: Bearer <jwt>``."""

    def dependency(authorization: str | None = Header(default=None)) -> CurrentUser:
        if not authorization:
            raise _unauthenticated()
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise _unauthenticated()
        return decode_access_token(token.strip(), get_secret())

    return dependency


def require_role(dependency: Callable[..., CurrentUser], *roles: str) -> Callable[..., CurrentUser]:
    """Wrap a current-user dependency so only the given roles pass (403 otherwise)."""

    def checker(user: CurrentUser = Depends(dependency)) -> CurrentUser:
        if user.role not in roles:
            raise AppError("FORBIDDEN", "Insufficient permissions", 403)
        return user

    return checker
