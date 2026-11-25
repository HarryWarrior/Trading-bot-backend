from mt5_bridge_service.application.ports.accounts import AccountRepository
from mt5_bridge_service.application.ports.journal import IngestDealsResult, JournalGateway
from mt5_bridge_service.domain.account import account_ref
from mt5_bridge_service.domain.deal import MAX_DEALS_PER_REQUEST, RawDeal
from mt5_bridge_service.domain.errors import InvalidDealBatch


class IngestDeals:
    def __init__(self, journal: JournalGateway, accounts: AccountRepository) -> None:
        self._journal = journal
        self._accounts = accounts

    async def execute(
        self, user_id: str, login: int, server: str, deals: list[RawDeal]
    ) -> IngestDealsResult:
        """Forward one EA batch of ``user_id`` (the token owner) to journal as ``login@server``.

        ``last_deal_at`` moves only after journal accepted the batch.

        Raises:
            InvalidDealBatch: If login/server are invalid or the batch exceeds the cap.
            JournalUnavailable: Journal is down; the EA must keep the batch and retry.
            JournalRejected: Journal refused the batch; retrying it cannot succeed.
        """
        clean_server = server.strip()
        if login <= 0 or not clean_server:
            raise InvalidDealBatch("Deals need a positive account login and a server name.")
        if len(deals) > MAX_DEALS_PER_REQUEST:
            raise InvalidDealBatch(f"At most {MAX_DEALS_PER_REQUEST} deals per request.")
        if not deals:
            return IngestDealsResult(received=0, new=0, trades_upserted=0)
        ref = account_ref(login, clean_server)
        result = await self._journal.ingest_deals(user_id, ref, deals)
        await self._accounts.touch_last_deal(user_id, ref, max(d.time for d in deals))
        return result
