"""JournalGateway backed by journal's service-key endpoint ``POST /api/v1/journal/ingest/deals``.

The owner is named in the body (``user_id``); the bridge authenticates with ``X-Service-Key``.
Neither the key nor any ingest token is ever logged.
"""

from __future__ import annotations

import logging
from datetime import UTC
from decimal import Decimal
from typing import Any

import httpx

from mt5_bridge_service.application.ports.journal import IngestDealsResult, SkippedPosition
from mt5_bridge_service.domain.deal import RawDeal
from mt5_bridge_service.domain.errors import JournalRejected, JournalUnavailable

logger = logging.getLogger(__name__)

INGEST_PATH = "/api/v1/journal/ingest/deals"
# Answers about the batch itself: resending it unchanged can never succeed.
REJECTION_STATUSES = frozenset({400, 409, 413, 422})


def _dec(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def deal_payload(deal: RawDeal) -> dict[str, Any]:
    """Journal's ``IngestDealIn``: UTC ISO 8601 time with ``Z``, decimals as exact strings."""
    return {
        "ticket": deal.ticket,
        "position_id": deal.position_id,
        "time": deal.time.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "type": deal.type,
        "entry": deal.entry,
        "symbol": deal.symbol,
        "volume": _dec(deal.volume),
        "price": _dec(deal.price),
        "commission": _dec(deal.commission),
        "swap": _dec(deal.swap),
        "fee": _dec(deal.fee),
        "profit": _dec(deal.profit),
        "sl": _dec(deal.sl),
        "tp": _dec(deal.tp),
        "comment": deal.comment,
    }


def _error_details(response: httpx.Response) -> Any:
    try:
        return response.json()["error"].get("details")
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


class JournalHttpGateway:
    def __init__(
        self,
        base_url: str,
        service_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_key = service_key
        self._transport = transport
        self._timeout = timeout

    async def ingest_deals(
        self, user_id: str, account_ref: str, deals: list[RawDeal]
    ) -> IngestDealsResult:
        payload = {
            "user_id": user_id,
            "account_ref": account_ref,
            "deals": [deal_payload(d) for d in deals],
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, transport=self._transport, timeout=self._timeout
            ) as client:
                response = await client.post(
                    INGEST_PATH, json=payload, headers={"X-Service-Key": self._service_key}
                )
        except httpx.HTTPError as exc:
            logger.warning("Journal request failed: %s", type(exc).__name__)
            raise JournalUnavailable("Journal is unreachable") from exc

        status = response.status_code
        if status in (401, 403):
            logger.error("Journal rejected service key: check INGEST_SERVICE_KEY on both services")
            raise JournalUnavailable("Journal rejected the service credentials")
        if status in REJECTION_STATUSES:
            tickets = [d.ticket for d in deals]
            logger.warning(
                "Journal rejected a batch of %d deals (tickets %d..%d): HTTP %s. "
                "To skip it, raise the EA high-water mark above the last ticket.",
                len(deals),
                min(tickets, default=0),
                max(tickets, default=0),
                status,
            )
            raise JournalRejected(details=_error_details(response))
        if not response.is_success:
            logger.warning("Journal answered HTTP %s", status)
            raise JournalUnavailable(f"Journal answered HTTP {status}")
        try:
            data = response.json()["data"]
            result = IngestDealsResult(
                received=int(data["received"]),
                new=int(data["new"]),
                trades_upserted=int(data["trades_upserted"]),
                balance_events=int(data.get("balance_events", 0)),
                skipped=tuple(
                    SkippedPosition(position_id=str(s["position_id"]), reason=str(s["reason"]))
                    for s in data.get("skipped", [])
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Journal sent an unusable ingest answer")
            raise JournalUnavailable("Journal sent an unusable answer") from exc
        if result.skipped:
            logger.warning(
                "Journal skipped %d positions: %s",
                len(result.skipped),
                [(s.position_id, s.reason) for s in result.skipped],
            )
        return result
