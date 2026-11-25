from dataclasses import dataclass

from mt5_bridge_service.application.ports.accounts import AccountRepository
from mt5_bridge_service.application.ports.clock import Clock
from mt5_bridge_service.domain.account import AccountStatus, BrokerAccount


@dataclass(frozen=True)
class AccountOverview:
    account: BrokerAccount
    status: AccountStatus


class ListAccounts:
    def __init__(self, accounts: AccountRepository, clock: Clock) -> None:
        self._accounts = accounts
        self._clock = clock

    async def execute(self, user_id: str) -> list[AccountOverview]:
        now = self._clock.now()
        return [
            AccountOverview(account=account, status=account.status(now))
            for account in await self._accounts.list_for_user(user_id)
        ]
