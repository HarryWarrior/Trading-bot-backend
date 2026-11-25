"""Port: where the dataset of a user comes from (the journal service in production)."""

from __future__ import annotations

from typing import Protocol

from analytics_service.domain.dataset import Dataset


class SourceUnavailable(Exception):
    """The data source cannot answer right now (down, timing out, or answering garbage)."""


class SourceUnauthenticated(Exception):
    """The data source rejected the caller token."""


class TradeSource(Protocol):
    async def fetch(self, token: str, account_ref: str | None) -> Dataset:
        """Return the caller dataset. ``token`` is the caller verified access token."""
        ...
