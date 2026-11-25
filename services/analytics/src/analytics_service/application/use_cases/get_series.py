from __future__ import annotations

from analytics_service.application.ports.trade_source import TradeSource
from analytics_service.domain import series
from analytics_service.domain.equity import EquityPoint, walk_equity
from analytics_service.domain.rounding import round_money


class GetSeries:
    def __init__(self, source: TradeSource) -> None:
        self._source = source

    async def equity(self, token: str, account_ref: str | None) -> list[EquityPoint]:
        """Equity curve; with a known starting balance it opens with that balance.

        The opening point sits at the time of the first balance event.
        """
        dataset = await self._source.fetch(token, account_ref)
        walk = walk_equity(dataset)
        points = [EquityPoint(p.time, round_money(p.equity)) for p in walk.points]
        if walk.starting_balance is not None and dataset.balance_events:
            first = min(event.time for event in dataset.balance_events)
            points.insert(0, EquityPoint(first, round_money(walk.starting_balance)))
        return points

    async def daily(self, token: str, account_ref: str | None) -> list[series.DailyStat]:
        return series.daily(await self._source.fetch(token, account_ref))

    async def monthly(self, token: str, account_ref: str | None) -> list[series.MonthlyStat]:
        return series.monthly(await self._source.fetch(token, account_ref))

    async def by_symbol(self, token: str, account_ref: str | None) -> list[series.SymbolStat]:
        return series.by_symbol(await self._source.fetch(token, account_ref))

    async def hourly(self, token: str, account_ref: str | None) -> list[series.HourStat]:
        return series.hourly(await self._source.fetch(token, account_ref))
