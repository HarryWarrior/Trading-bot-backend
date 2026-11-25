from journal_service.application.ports.repositories import TradeRepository
from journal_service.domain.errors import TradeNotFound
from journal_service.domain.trade import Trade


class GetTrade:
    def __init__(self, trades: TradeRepository) -> None:
        self._trades = trades

    async def execute(self, user_id: str, trade_id: str) -> Trade:
        trade = await self._trades.get(user_id, trade_id)
        if trade is None:
            raise TradeNotFound(trade_id)
        return trade
