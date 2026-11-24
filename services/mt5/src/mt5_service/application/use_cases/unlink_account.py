from mt5_service.application.ports.repositories import LinkedAccountRepository
from mt5_service.domain.errors import AccountNotFound


class UnlinkAccount:
    """Removes the link only; trades already in journal are kept."""

    def __init__(self, accounts: LinkedAccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, user_id: str, account_id: str) -> None:
        if not await self._accounts.delete(user_id, account_id):
            raise AccountNotFound(account_id)
