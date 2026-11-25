"""Composition root: the only place that knows which adapter implements which port."""

from dataclasses import dataclass

from analytics_service.adapters.outbound.journal_client import JournalHttpTradeSource
from analytics_service.application.ports.trade_source import TradeSource
from analytics_service.application.use_cases.get_series import GetSeries
from analytics_service.application.use_cases.get_summary import GetSummary
from analytics_service.settings import AnalyticsSettings


@dataclass(frozen=True)
class Container:
    settings: AnalyticsSettings
    get_summary: GetSummary
    get_series: GetSeries


def build_container(
    settings: AnalyticsSettings, trade_source: TradeSource | None = None
) -> Container:
    source = trade_source or JournalHttpTradeSource(settings.journal_url)
    return Container(
        settings=settings, get_summary=GetSummary(source), get_series=GetSeries(source)
    )
