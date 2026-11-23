from auth_service.application.ports.clock import Clock
from auth_service.application.ports.email import EmailSender
from auth_service.application.ports.repositories import PasswordResetRepository, UserRepository
from auth_service.application.ports.security import SecretGenerator
from auth_service.domain.tokens import RESET_TOKEN_TTL, digest
from auth_service.domain.user import normalize_email


class ForgotPassword:
    def __init__(
        self,
        users: UserRepository,
        resets: PasswordResetRepository,
        secrets: SecretGenerator,
        email_sender: EmailSender,
        clock: Clock,
    ) -> None:
        self._users = users
        self._resets = resets
        self._secrets = secrets
        self._email = email_sender
        self._clock = clock

    async def execute(self, email: str) -> None:
        """Email a single-use reset token. Silent for unknown emails (no enumeration)."""
        normalized = normalize_email(email)
        user = await self._users.get_by_email(normalized)
        if user is None:
            return
        token = self._secrets.opaque_token()
        await self._resets.add(user.id, digest(token), self._clock.now() + RESET_TOKEN_TTL)
        await self._email.send_password_reset(normalized, token)
