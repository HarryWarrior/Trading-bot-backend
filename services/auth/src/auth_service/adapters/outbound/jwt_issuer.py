"""HS256 access-token issuer (adapter for the AccessTokenIssuer port)."""

from datetime import UTC, datetime, timedelta

import jwt

from auth_service.domain.user import User

ALGORITHM = "HS256"


class JwtAccessTokenIssuer:
    def __init__(self, secret: str, minutes: int = 15) -> None:
        if not secret or not secret.strip():
            raise ValueError("JWT secret is not configured")
        self._secret = secret
        self._minutes = minutes

    def issue(self, user: User) -> tuple[str, int]:
        issued_at = datetime.now(UTC)
        lifetime = timedelta(minutes=self._minutes)
        claims = {
            "sub": user.id,
            "email": user.email,
            "role": str(user.role.value),
            "iat": issued_at,
            "exp": issued_at + lifetime,
        }
        return jwt.encode(claims, self._secret, algorithm=ALGORITHM), int(lifetime.total_seconds())
