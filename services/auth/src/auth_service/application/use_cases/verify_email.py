from auth_service.application.ports.clock import Clock
from auth_service.application.ports.repositories import UserRepository, VerificationRepository
from auth_service.domain.errors import InvalidVerificationCode
from auth_service.domain.tokens import digest
from auth_service.domain.user import normalize_email


class VerifyEmail:
    def __init__(
        self, users: UserRepository, verifications: VerificationRepository, clock: Clock
    ) -> None:
        self._users = users
        self._verifications = verifications
        self._clock = clock

    async def execute(self, email: str, code: str) -> None:
        """Consume a verification code and mark the account verified.

        Raises:
            InvalidVerificationCode: If the code is wrong, expired or already used.
        """
        normalized = normalize_email(email)
        user = await self._users.get_by_email(normalized)
        consumed = await self._verifications.consume(
            normalized, digest(code.strip()), self._clock.now()
        )
        if user is None or not consumed:
            raise InvalidVerificationCode("Invalid or expired verification code.")
        await self._users.mark_verified(user.id)
