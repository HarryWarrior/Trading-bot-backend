"""TradeSource backed by the journal service HTTP API."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from analytics_service.application.ports.trade_source import (
    SourceUnauthenticated,
    SourceUnavailable,
)
from analytics_service.domain.dataset import BalanceRecord, Dataset, TradeRecord

logger = logging.getLogger(__name__)

DATASET_PATH = "/api/v1/journal/dataset"


def _aware_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("journal sent a datetime without timezone")
    return parsed


def _money(value: Any) -> Decimal:
    # Journal sends money as JSON numbers already rounded to 2 dp.
    return Decimal(str(value))


def _parse(payload: Any) -> Dataset:
    data = payload["data"]
    trades = [
        TradeRecord(
            symbol=row["symbol"],
            side=row["side"],
            open_time=_aware_datetime(row["open_time"]),
            close_time=_aware_datetime(row["close_time"]),
            net=_money(row["net"]),
        )
        for row in data["trades"]
    ]
    events = [
        BalanceRecord(time=_aware_datetime(row["time"]), amount=_money(row["amount"]))
        for row in data["balance_events"]
    ]
    return Dataset(trades=trades, balance_events=events)


class JournalHttpTradeSource:
    def __init__(
        self,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    async def fetch(self, token: str, account_ref: str | None) -> Dataset:
        params = {"account_ref": account_ref} if account_ref is not None else None
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, transport=self._transport, timeout=self._timeout
            ) as client:
                response = await client.get(
                    DATASET_PATH, params=params, headers={"Authorization": f"Bearer {token}"}
                )
        except httpx.HTTPError as exc:
            logger.warning("Journal request failed: %s", type(exc).__name__)
            raise SourceUnavailable("Journal is unreachable") from exc

        if response.status_code == 401:
            raise SourceUnauthenticated("Journal rejected the access token")
        if not response.is_success:
            logger.warning("Journal answered HTTP %s", response.status_code)
            raise SourceUnavailable(f"Journal answered HTTP {response.status_code}")
        try:
            return _parse(response.json())
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            logger.warning("Journal sent an unusable dataset (shape or timezone): %s", exc)
            raise SourceUnavailable("Journal sent an unusable dataset") from exc
