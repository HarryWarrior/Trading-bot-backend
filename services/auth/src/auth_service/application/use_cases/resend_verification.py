from auth_service.application.ports.clock import Clock
from auth_service.application.ports.email import EmailSender
from auth_service.application.ports.repositories import UserRepository, VerificationRepository
from auth_service.application.ports.security import SecretGenerator
from auth_service.domain.tokens import VERIFICATION_CODE_TTL, digest
from auth_service.domain.user import normalize_email


class ResendVerification:
    def __init__(
        self,
        users: UserRepository,
        verifications: VerificationRepository,
        secrets: SecretGenerator,
        email_sender: EmailSender,
        clock: Clock,
    ) -> None:
        self._users = users
        self._verifications = verifications
        self._secrets = secrets
        self._email = email_sender
        self._clock = clock

    async def execute(self, email: str) -> None:
        """Send a fresh code to an unverified account. Silent for unknown or verified emails."""
        normalized = normalize_email(email)
        user = await self._users.get_by_email(normalized)
        if user is None or user.email_verified:
            return
        code = self._secrets.verification_code()
        await self._verifications.replace_code(
            normalized, digest(code), self._clock.now() + VERIFICATION_CODE_TTL
        )
        await self._email.send_verification(normalized, code)
