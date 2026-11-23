from auth_service.application.ports.clock import Clock
from auth_service.application.ports.repositories import SessionRepository, UserRepository
from auth_service.application.ports.security import AccessTokenIssuer, SecretGenerator
from auth_service.application.use_cases.session_issue import open_session
from auth_service.domain.errors import InvalidToken
from auth_service.domain.tokens import AuthTokens, digest


class RefreshSession:
    def __init__(
        self,
        users: UserRepository,
        sessions: SessionRepository,
        issuer: AccessTokenIssuer,
        secrets: SecretGenerator,
        clock: Clock,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._issuer = issuer
        self._secrets = secrets
        self._clock = clock

    async def execute(self, refresh_token: str) -> AuthTokens:
        """Rotate a refresh token: the presented one is consumed and a new pair is issued.

        Raises:
            InvalidToken: If the token is unknown, expired, revoked or already used.
        """
        user_id = await self._sessions.consume(digest(refresh_token), self._clock.now())
        user = await self._users.get_by_id(user_id) if user_id else None
        if user is None:
            raise InvalidToken("Invalid or expired refresh token.")
        return await open_session(user, self._sessions, self._issuer, self._secrets, self._clock)
