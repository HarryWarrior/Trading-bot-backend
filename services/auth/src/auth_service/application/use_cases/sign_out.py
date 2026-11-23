from auth_service.application.ports.repositories import SessionRepository
from auth_service.domain.tokens import digest


class SignOut:
    def __init__(self, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def execute(self, refresh_token: str) -> None:
        """Revoke the session of the refresh token. Idempotent."""
        await self._sessions.revoke(digest(refresh_token))
