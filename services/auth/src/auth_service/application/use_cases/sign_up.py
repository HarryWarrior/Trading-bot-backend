from uuid import uuid4

from auth_service.application.ports.clock import Clock
from auth_service.application.ports.email import EmailSender
from auth_service.application.ports.repositories import UserRepository, VerificationRepository
from auth_service.application.ports.security import PasswordHasher, SecretGenerator
from auth_service.domain.errors import EmailAlreadyRegistered
from auth_service.domain.tokens import VERIFICATION_CODE_TTL, digest
from auth_service.domain.user import Role, User, normalize_email


class SignUp:
    def __init__(
        self,
        users: UserRepository,
        verifications: VerificationRepository,
        hasher: PasswordHasher,
        secrets: SecretGenerator,
        email_sender: EmailSender,
        clock: Clock,
    ) -> None:
        self._users = users
        self._verifications = verifications
        self._hasher = hasher
        self._secrets = secrets
        self._email = email_sender
        self._clock = clock

    async def execute(self, email: str, password: str, name: str) -> User:
        """Register an unverified user and email a verification code.

        Raises:
            EmailAlreadyRegistered: If the normalized email already has an account.
        """
        normalized = normalize_email(email)
        if await self._users.get_by_email(normalized) is not None:
            raise EmailAlreadyRegistered("Email is already registered.")
        now = self._clock.now()
        user = User(
            id=uuid4().hex,
            email=normalized,
            name=name.strip(),
            role=Role.USER,
            password_hash=self._hasher.hash(password),
            email_verified=False,
            created_at=now,
        )
        await self._users.add(user)
        code = self._secrets.verification_code()
        await self._verifications.replace_code(
            normalized, digest(code), now + VERIFICATION_CODE_TTL
        )
        await self._email.send_verification(normalized, code)
        return user
