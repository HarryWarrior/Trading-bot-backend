from mt5_bridge_service.application.ports.accounts import AccountRepository
from mt5_bridge_service.application.ports.clock import Clock
from mt5_bridge_service.domain.account import BrokerAccount, Heartbeat


class RecordHeartbeat:
    def __init__(self, accounts: AccountRepository, clock: Clock) -> None:
        self._accounts = accounts
        self._clock = clock

    async def execute(self, user_id: str, hb: Heartbeat) -> BrokerAccount:
        """Upsert the account ``login@server`` of ``user_id`` with the reported state.

        Raises:
            InvalidHeartbeat: If the heartbeat has no valid login/server.
        """
        account = BrokerAccount.from_heartbeat(user_id, hb, self._clock.now())
        return await self._accounts.upsert_heartbeat(account)
