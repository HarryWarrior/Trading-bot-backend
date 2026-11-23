"""JournalHttpTradeSource against a mocked journal (httpx.MockTransport)."""

from __future__ import annotations

import logging
from decimal import Decimal

import httpx
import pytest

from analytics_service.adapters.outbound.journal_client import JournalHttpTradeSource
from analytics_service.application.ports.trade_source import (
    SourceUnauthenticated,
    SourceUnavailable,
)

TRADE = {
    "symbol": "EURUSD",
    "side": "buy",
    "open_time": "2026-01-05T09:00:00Z",
    "close_time": "2026-01-05T10:00:00Z",
    "net": 12.34,
}
EVENT = {"time": "2026-01-01T00:00:00+00:00", "amount": -5.5}


def source_for(handler) -> JournalHttpTradeSource:
    return JournalHttpTradeSource("http://journal.test/", transport=httpx.MockTransport(handler))


def ok_payload(trades=None, events=None) -> dict:
    return {"success": True, "data": {"trades": trades or [], "balance_events": events or []}}


async def test_maps_payload_forwards_header_and_query():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json=ok_payload([TRADE], [EVENT]))

    dataset = await source_for(handler).fetch("tok.en", "123@Live")
    assert seen["auth"] == "Bearer tok.en"
    assert seen["url"] == "http://journal.test/api/v1/journal/dataset?account_ref=123%40Live"
    assert dataset.trades[0].net == Decimal("12.34")
    assert dataset.trades[0].close_time.utcoffset() is not None
    assert dataset.balance_events[0].amount == Decimal("-5.5")


async def test_account_ref_omitted_when_none():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = request.url.query
        return httpx.Response(200, json=ok_payload())

    await source_for(handler).fetch("t", None)
    assert seen["query"] == b""


async def test_401_maps_to_unauthenticated():
    with pytest.raises(SourceUnauthenticated):
        await source_for(lambda r: httpx.Response(401, json={})).fetch("t", None)


@pytest.mark.parametrize("status", [500, 502, 503, 404, 403, 422])
async def test_other_failures_are_unavailable(status):
    with pytest.raises(SourceUnavailable):
        await source_for(lambda r: httpx.Response(status, json={})).fetch("t", None)


async def test_connection_error_and_timeout_are_unavailable():
    def refuse(request):
        raise httpx.ConnectError("refused")

    def slow(request):
        raise httpx.ReadTimeout("slow")

    for handler in (refuse, slow):
        with pytest.raises(SourceUnavailable):
            await source_for(handler).fetch("t", None)


async def test_naive_datetime_is_rejected(caplog):
    naive = {**TRADE, "close_time": "2026-01-05T10:00:00"}
    with caplog.at_level(logging.WARNING), pytest.raises(SourceUnavailable):
        await source_for(lambda r: httpx.Response(200, json=ok_payload([naive]))).fetch("t", None)
    assert "timezone" in caplog.text


@pytest.mark.parametrize("body", [{"nope": 1}, {"data": {"trades": [{"symbol": "X"}]}}])
async def test_malformed_payload_is_unavailable(body):
    with pytest.raises(SourceUnavailable):
        await source_for(lambda r: httpx.Response(200, json=body)).fetch("t", None)


async def test_token_is_never_logged(caplog):
    with caplog.at_level(logging.DEBUG), pytest.raises(SourceUnavailable):
        await source_for(lambda r: httpx.Response(500)).fetch("secret-token-value", None)
    assert "secret-token-value" not in caplog.text
