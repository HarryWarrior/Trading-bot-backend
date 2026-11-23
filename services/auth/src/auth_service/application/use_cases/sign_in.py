from auth_service.application.ports.clock import Clock
from auth_service.application.ports.repositories import SessionRepository, UserRepository
from auth_service.application.ports.security import (
    AccessTokenIssuer,
    PasswordHasher,
    SecretGenerator,
)
from auth_service.application.use_cases.session_issue import open_session
from auth_service.domain.errors import EmailNotVerified, InvalidCredentials
from auth_service.domain.tokens import AuthTokens
from auth_service.domain.user import normalize_email


class SignIn:
    def __init__(
        self,
        users: UserRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        issuer: AccessTokenIssuer,
        secrets: SecretGenerator,
        clock: Clock,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._issuer = issuer
        self._secrets = secrets
        self._clock = clock

    async def execute(self, email: str, password: str) -> AuthTokens:
        """Authenticate and open a session.

        Raises:
            InvalidCredentials: Unknown email or wrong password (indistinguishable).
            EmailNotVerified: Correct credentials but the email is not verified yet.
        """
        user = await self._users.get_by_email(normalize_email(email))
        if user is None or not self._hasher.verify(password, user.password_hash):
            raise InvalidCredentials("Invalid email or password.")
        if not user.email_verified:
            raise EmailNotVerified("Email is not verified.")
        return await open_session(user, self._sessions, self._issuer, self._secrets, self._clock)
