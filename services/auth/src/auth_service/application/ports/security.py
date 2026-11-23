from typing import Protocol

from auth_service.domain.user import User


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class AccessTokenIssuer(Protocol):
    def issue(self, user: User) -> tuple[str, int]:
        """Return the signed access token and its lifetime in seconds."""
        ...


class SecretGenerator(Protocol):
    def verification_code(self) -> str: ...

    def opaque_token(self) -> str: ...
