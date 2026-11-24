from mt5_service.application.ports.repositories import LinkedAccountRepository
from mt5_service.domain.account import LinkedAccount


class ListAccounts:
    def __init__(self, accounts: LinkedAccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, user_id: str) -> list[LinkedAccount]:
        return await self._accounts.list(user_id)
