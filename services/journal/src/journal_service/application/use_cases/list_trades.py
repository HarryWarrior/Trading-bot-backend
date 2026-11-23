from dataclasses import replace

from journal_service.application.ports.repositories import TradeFilters, TradeRepository
from journal_service.domain.trade import Trade
from trading_shared.envelope import PageParams


class ListTrades:
    def __init__(self, trades: TradeRepository) -> None:
        self._trades = trades

    async def execute(
        self, user_id: str, filters: TradeFilters, params: PageParams
    ) -> tuple[list[Trade], int]:
        if filters.q is None and params.q:
            filters = replace(filters, q=params.q)
        return await self._trades.list(
            user_id, filters, params.page, params.page_size, params.sort_by, params.sort_dir
        )
