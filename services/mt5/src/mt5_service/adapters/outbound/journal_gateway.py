"""JournalGateway backed by the journal service HTTP API.

Sends the caller's own access token (journal scopes data by it) plus the shared service key.
Neither the token nor the key is ever logged.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from mt5_service.application.ports.journal import IngestResult
from mt5_service.domain.errors import JournalUnavailable, Unauthenticated
from mt5_service.domain.trades import BalanceEventOut, TradeOut

logger = logging.getLogger(__name__)

INGEST_PATH = "/api/v1/journal/ingest/mt5"


class JournalHttpGateway:
    def __init__(
        self,
        base_url: str,
        service_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_key = service_key
        self._transport = transport
        self._timeout = timeout

    async def ingest(
        self,
        token: str,
        account_ref: str,
        trades: list[TradeOut],
        balance_events: list[BalanceEventOut],
    ) -> IngestResult:
        payload: dict[str, Any] = {
            "account_ref": account_ref,
            "trades": [t.to_payload() for t in trades],
            "balance_events": [e.to_payload() for e in balance_events],
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, transport=self._transport, timeout=self._timeout
            ) as client:
                response = await client.post(
                    INGEST_PATH,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Service-Key": self._service_key,
                    },
                )
        except httpx.HTTPError as exc:
            logger.warning("Journal request failed: %s", type(exc).__name__)
            raise JournalUnavailable("Journal is unreachable") from exc

        if response.status_code == 401:
            raise Unauthenticated("Journal rejected the access token")
        if response.status_code == 403:
            logger.error("Journal rejected service key: check INGEST_SERVICE_KEY on both services")
            raise JournalUnavailable("Journal rejected the service credentials")
        if not response.is_success:
            logger.warning("Journal answered HTTP %s", response.status_code)
            raise JournalUnavailable(f"Journal answered HTTP {response.status_code}")
        try:
            data = response.json()["data"]
            return IngestResult(
                created=int(data["created"]),
                updated=int(data["updated"]),
                balance_events=int(data["balance_events"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Journal sent an unusable ingest answer")
            raise JournalUnavailable("Journal sent an unusable answer") from exc
