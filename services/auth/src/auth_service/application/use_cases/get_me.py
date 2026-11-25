from auth_service.application.ports.repositories import UserRepository
from auth_service.domain.errors import InvalidToken
from auth_service.domain.user import User


class GetMe:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, user_id: str) -> User:
        """Return the authenticated user.

        Raises:
            InvalidToken: If the user no longer exists.
        """
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise InvalidToken("User not found.")
        return user
