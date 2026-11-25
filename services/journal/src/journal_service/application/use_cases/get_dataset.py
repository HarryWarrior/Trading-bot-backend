from dataclasses import dataclass

from journal_service.application.ports.repositories import BalanceRepository, TradeRepository
from journal_service.domain.balance import BalanceEvent
from journal_service.domain.trade import Trade


@dataclass(frozen=True)
class Dataset:
    trades: list[Trade]
    balance_events: list[BalanceEvent]


class GetDataset:
    def __init__(self, trades: TradeRepository, balances: BalanceRepository) -> None:
        self._trades = trades
        self._balances = balances

    async def execute(self, user_id: str, account_ref: str | None) -> Dataset:
        return Dataset(
            trades=await self._trades.all_for(user_id, account_ref),
            balance_events=await self._balances.all_for(user_id, account_ref),
        )
