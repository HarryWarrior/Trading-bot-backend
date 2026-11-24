"""Composition root: the only place that knows which adapter implements which port.

Adapters and use-case wiring are added in later tasks; for now it only carries the settings.
"""

from dataclasses import dataclass

from mt5_service.settings import Mt5Settings


@dataclass(frozen=True)
class Container:
    settings: Mt5Settings


def build_container(settings: Mt5Settings) -> Container:
    return Container(settings=settings)
