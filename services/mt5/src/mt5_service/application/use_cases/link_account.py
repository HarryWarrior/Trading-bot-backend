from mt5_service.application.ports.clock import Clock
from mt5_service.application.ports.ids import IdGenerator
from mt5_service.application.ports.repositories import LinkedAccountRepository
from mt5_service.application.ports.terminal import BrokerTerminal
from mt5_service.domain.account import LinkedAccount
from mt5_service.domain.errors import AccountAlreadyLinked


class LinkAccount:
    """Links whatever account the running terminal reports. No credentials are involved."""

    def __init__(
        self,
        terminal: BrokerTerminal,
        accounts: LinkedAccountRepository,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._terminal = terminal
        self._accounts = accounts
        self._clock = clock
        self._ids = ids

    async def execute(self, user_id: str) -> LinkedAccount:
        current = await self._terminal.current_account()
        existing = await self._accounts.find_by_ref(current.account_ref)
        if existing is not None:
            if existing.user_id != user_id:
                raise AccountAlreadyLinked(current.account_ref)
            return existing
        account = LinkedAccount(
            id=self._ids.new_id(),
            user_id=user_id,
            account_ref=current.account_ref,
            login=current.login,
            server=current.server,
            name=current.name,
            currency=current.currency,
            trade_mode=current.trade_mode,
            company=current.company,
            linked_at=self._clock.now(),
        )
        # The repository enforces the unique account_ref and raises AccountAlreadyLinked on a race.
        await self._accounts.add(account)
        return account
