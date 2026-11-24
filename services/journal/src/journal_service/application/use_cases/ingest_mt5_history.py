from dataclasses import dataclass

from journal_service.application.ports.ids import IdGenerator
from journal_service.application.ports.parsing import ParsedBalanceEvent, ParsedTrade
from journal_service.application.ports.repositories import BalanceRepository, TradeRepository
from journal_service.application.use_cases._build import build_balance_event, build_trade


@dataclass(frozen=True)
class IngestResult:
    created: int
    updated: int
    balance_events: int  # new balance events only


class IngestMt5History:
    def __init__(
        self, trades: TradeRepository, balances: BalanceRepository, ids: IdGenerator
    ) -> None:
        self._trades = trades
        self._balances = balances
        self._ids = ids

    async def execute(
        self,
        user_id: str,
        account_ref: str,
        trades: list[ParsedTrade],
        balance_events: list[ParsedBalanceEvent],
    ) -> IngestResult:
        built = [
            build_trade(
                t,
                user_id=user_id,
                account_ref=account_ref,
                source="mt5",
                import_id=None,
                ids=self._ids,
            )
            for t in trades
        ]
        events = [
            build_balance_event(e, user_id=user_id, account_ref=account_ref, ids=self._ids)
            for e in balance_events
        ]
        created, updated = await self._trades.upsert_many(user_id, built)
        count = await self._balances.upsert_many(user_id, events)
        return IngestResult(created=created, updated=updated, balance_events=count)
