"""Composition root: the only place that knows which adapter implements which port.

Adapters (Mongo, parsers) and the use-case container arrive in tasks 2-4.
"""

from dataclasses import dataclass

from journal_service.settings import JournalSettings


@dataclass(frozen=True)
class Container:
    settings: JournalSettings


def build_container(settings: JournalSettings) -> Container:
    return Container(settings=settings)
