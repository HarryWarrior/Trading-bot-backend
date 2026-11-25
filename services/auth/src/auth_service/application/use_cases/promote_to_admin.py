from auth_service.application.ports.repositories import UserRepository
from auth_service.domain.errors import AuthError
from auth_service.domain.user import Role, normalize_email


class UserNotFound(AuthError):
    code = "USER_NOT_FOUND"
    http_status = 404


class PromoteToAdmin:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, email: str) -> None:
        """Grant the admin role.

        Raises:
            UserNotFound: If no user has that (normalized) email.
        """
        user = await self._users.get_by_email(normalize_email(email))
        if user is None:
            raise UserNotFound("No user with that email.")
        await self._users.set_role(user.id, Role.ADMIN)
