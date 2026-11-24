from mt5_service.application.ports.clock import Clock
from mt5_service.application.ports.journal import JournalGateway
from mt5_service.application.ports.repositories import LinkedAccountRepository
from mt5_service.application.ports.terminal import BrokerTerminal
from mt5_service.domain.account import SyncResult
from mt5_service.domain.errors import AccountNotFound, TerminalAccountMismatch
from mt5_service.domain.time import server_offset
from mt5_service.domain.trades import build_trades


class SyncAccount:
    """Reads the full deal history and upserts closed trades into journal (idempotent)."""

    def __init__(
        self,
        terminal: BrokerTerminal,
        journal: JournalGateway,
        accounts: LinkedAccountRepository,
        clock: Clock,
    ) -> None:
        self._terminal = terminal
        self._journal = journal
        self._accounts = accounts
        self._clock = clock

    async def execute(self, user_id: str, account_id: str, token: str) -> SyncResult:
        account = await self._accounts.get(user_id, account_id)
        if account is None:
            raise AccountNotFound(account_id)
        current = await self._terminal.current_account()  # TerminalNotAvailable propagates
        if current.account_ref != account.account_ref:
            raise TerminalAccountMismatch(account.account_ref, current.account_ref)

        deals = await self._terminal.history_deals()
        now = self._clock.now()
        offset = server_offset(await self._terminal.latest_tick_time(None), now)
        built = build_trades(deals, offset)
        ingested = await self._journal.ingest(
            token, account.account_ref, built.trades, built.balance_events
        )
        result = SyncResult(
            created=ingested.created,
            updated=ingested.updated,
            balance_events=ingested.balance_events,
            open_positions=built.open_positions,
            skipped_positions=len(built.skipped_positions),
        )
        await self._accounts.mark_synced(account.id, now, result)
        return result
