"""Composition root. Adapters are wired in a later task (planned)."""

from dataclasses import dataclass

from auth_service.settings import AuthSettings


@dataclass(frozen=True)
class Container:
    settings: AuthSettings


def build_container(settings: AuthSettings) -> Container:
    return Container(settings=settings)
