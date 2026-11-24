from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from mt5_service.application.ports.clock import Clock
from mt5_service.application.ports.repositories import LinkedAccountRepository
from mt5_service.application.ports.terminal import BrokerTerminal
from mt5_service.domain.errors import AccountNotFound, TerminalNotAvailable


@dataclass(frozen=True)
class AccountStatus:
    connected: bool
    balance: Decimal | None
    equity: Decimal | None
    as_of: datetime | None
    last_sync_at: datetime | None


class GetStatus:
    """``connected`` only when the terminal reports this very account right now.

    Balance, equity and as_of come from the live terminal or are None: never stored or defaulted.
    """

    def __init__(
        self, terminal: BrokerTerminal, accounts: LinkedAccountRepository, clock: Clock
    ) -> None:
        self._terminal = terminal
        self._accounts = accounts
        self._clock = clock

    async def execute(self, user_id: str, account_id: str) -> AccountStatus:
        account = await self._accounts.get(user_id, account_id)
        if account is None:
            raise AccountNotFound(account_id)
        try:
            current = await self._terminal.current_account()
        except TerminalNotAvailable:
            return AccountStatus(False, None, None, None, account.last_sync_at)
        if current.account_ref != account.account_ref:
            return AccountStatus(False, None, None, None, account.last_sync_at)
        return AccountStatus(
            True, current.balance, current.equity, self._clock.now(), account.last_sync_at
        )
