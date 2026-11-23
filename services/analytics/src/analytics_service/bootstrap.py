"""Composition root: wires adapters into use cases (filled in by the HTTP task)."""

from dataclasses import dataclass

from analytics_service.settings import AnalyticsSettings


@dataclass(frozen=True)
class Container:
    settings: AnalyticsSettings


def build_container(settings: AnalyticsSettings) -> Container:
    return Container(settings=settings)
