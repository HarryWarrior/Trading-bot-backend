from auth_service.application.ports.clock import Clock
from auth_service.application.ports.repositories import (
    PasswordResetRepository,
    SessionRepository,
    UserRepository,
)
from auth_service.application.ports.security import PasswordHasher
from auth_service.domain.errors import InvalidToken
from auth_service.domain.tokens import digest


class ResetPassword:
    def __init__(
        self,
        users: UserRepository,
        resets: PasswordResetRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        clock: Clock,
    ) -> None:
        self._users = users
        self._resets = resets
        self._sessions = sessions
        self._hasher = hasher
        self._clock = clock

    async def execute(self, token: str, new_password: str) -> None:
        """Set a new password with a single-use token and revoke every session of the user.

        Raises:
            InvalidToken: If the token is unknown, expired or already used.
        """
        user_id = await self._resets.consume(digest(token), self._clock.now())
        if user_id is None:
            raise InvalidToken("Invalid or expired reset token.")
        await self._users.set_password_hash(user_id, self._hasher.hash(new_password))
        await self._sessions.revoke_all(user_id)
