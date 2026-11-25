from __future__ import annotations

from analytics_service.application.ports.trade_source import TradeSource
from analytics_service.domain.summary import Summary, summarize


class GetSummary:
    def __init__(self, source: TradeSource) -> None:
        self._source = source

    async def execute(self, token: str, account_ref: str | None) -> Summary:
        return summarize(await self._source.fetch(token, account_ref))
