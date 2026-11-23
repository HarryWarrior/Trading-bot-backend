from auth_service.application.ports.clock import Clock
from auth_service.application.ports.repositories import SessionRepository


class CleanupExpiredSessions:
    def __init__(self, sessions: SessionRepository, clock: Clock) -> None:
        self._sessions = sessions
        self._clock = clock

    async def execute(self) -> int:
        """Delete expired sessions and return how many were removed."""
        return await self._sessions.delete_expired(self._clock.now())
