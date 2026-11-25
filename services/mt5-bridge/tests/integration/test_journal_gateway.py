"""JournalHttpGateway against the REAL journal app (throwaway DB) and against canned answers."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import jwt
import pytest
from pymongo import MongoClient

from journal_service.main import create_app as create_journal_app
from journal_service.settings import JournalSettings
from mt5_bridge_service.adapters.outbound.journal_gateway import JournalHttpGateway
from mt5_bridge_service.domain.deal import RawDeal
from mt5_bridge_service.domain.errors import JournalRejected, JournalUnavailable

MONGO_URL = "mongodb://localhost:27017"
SECRET = "test-secret-key-with-enough-length-0123456789"
SERVICE_KEY = "test-ingest-service-key-with-enough-length-0123456789"
REF = "123456@Demo-Server"
T0 = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)


def deal(ticket: int, entry: int, time: datetime, **extra) -> RawDeal:
    values = dict(
        ticket=ticket,
        position_id=7,
        time=time,
        type=0 if entry == 0 else 1,
        entry=entry,
        symbol="EURUSD",
        volume=Decimal("1.0"),
        price=Decimal("1.1000") if entry == 0 else Decimal("1.1050"),
        commission=Decimal("-2"),
        swap=Decimal("0"),
        profit=Decimal("0") if entry == 0 else Decimal("50"),
        sl=None,
        tp=None,
        comment=None,
    )
    values.update(extra)
    return RawDeal(**values)


ENTRY = deal(1, 0, T0, sl=Decimal("1.09"), comment="go")
EXIT = deal(2, 1, T0 + timedelta(hours=1), fee=Decimal("-0.5"))


def token(user_id: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "email": f"{user_id}@mail.com",
        "role": "user",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(claims, SECRET, algorithm="HS256")


@pytest.fixture
def database_name():
    sync_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=1000)
    try:
        sync_client.admin.command("ping")
    except Exception:
        sync_client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    name = f"test_bridge_journal_{uuid.uuid4().hex}"
    try:
        yield name
    finally:
        sync_client.drop_database(name)
        sync_client.close()


@pytest.fixture
async def journal_transport(database_name):
    app = create_journal_app(
        JournalSettings(
            _env_file=None,
            environment="test",
            database_name=database_name,
            mongodb_url=MONGO_URL,
            jwt_secret_key=SECRET,
            ingest_service_key=SERVICE_KEY,
        )
    )
    async with app.router.lifespan_context(app):
        yield httpx.ASGITransport(app=app)


async def trades(transport, user_id: str) -> list[dict]:
    async with httpx.AsyncClient(transport=transport, base_url="http://journal.test") as client:
        response = await client.get(
            "/api/v1/journal/trades", headers={"Authorization": f"Bearer {token(user_id)}"}
        )
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


def gateway(transport, key: str = SERVICE_KEY) -> JournalHttpGateway:
    return JournalHttpGateway("http://journal.test", key, transport=transport)


async def test_forwarded_deals_become_one_trade_of_the_owner_only(journal_transport):
    gw = gateway(journal_transport)
    first = await gw.ingest_deals("alice", REF, [ENTRY, EXIT])
    assert (first.received, first.new, first.trades_upserted) == (2, 2, 1)
    again = await gw.ingest_deals("alice", REF, [ENTRY, EXIT])
    assert (again.received, again.new) == (2, 0)

    [trade] = await trades(journal_transport, "alice")
    assert trade["account_ref"] == REF
    assert trade["position_id"] == "7"
    assert await trades(journal_transport, "bob") == []


async def test_wrong_service_key_is_unavailable_and_never_logged(journal_transport, caplog):
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(JournalUnavailable):
            await gateway(journal_transport, key="y" * 40).ingest_deals("alice", REF, [ENTRY])
    assert "INGEST_SERVICE_KEY" in caplog.text
    assert "y" * 40 not in caplog.text
    assert await trades(journal_transport, "alice") == []


def capture(status: int, body: dict | None = None, seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=body if body is not None else {})

    return httpx.MockTransport(handler)


OK_BODY = {
    "success": True,
    "data": {"received": 1, "new": 1, "trades_upserted": 0, "balance_events": 0, "skipped": []},
}


async def test_payload_has_owner_utc_iso_times_and_decimal_strings():
    seen: list[httpx.Request] = []
    local = deal(1, 0, datetime(2026, 3, 2, 10, 0, tzinfo=timezone(timedelta(hours=2))))
    await gateway(capture(200, OK_BODY, seen)).ingest_deals("alice", REF, [local, EXIT])

    [request] = seen
    assert request.url.path == "/api/v1/journal/ingest/deals"
    assert request.headers["x-service-key"] == SERVICE_KEY
    assert "authorization" not in request.headers
    payload = json.loads(request.content)
    assert (payload["user_id"], payload["account_ref"]) == ("alice", REF)
    first, second = payload["deals"]
    assert first["time"] == "2026-03-02T08:00:00Z"
    assert first["volume"] == "1.0"
    assert first["price"] == "1.1000"
    assert first["sl"] is None
    assert second["fee"] == "-0.5"
    assert second["ticket"] == 2


@pytest.mark.parametrize("status", [500, 502, 503, 504, 401, 403, 404, 429])
async def test_server_errors_and_misconfiguration_are_unavailable(status):
    with pytest.raises(JournalUnavailable):
        await gateway(capture(status)).ingest_deals("alice", REF, [ENTRY])


@pytest.mark.parametrize("status", [400, 409, 413, 422])
async def test_client_rejections_are_journal_rejected_with_details(status):
    body = {
        "success": False,
        "error": {"code": "VALIDATION_ERROR", "message": "m", "details": [{"loc": ["x"]}]},
    }
    with pytest.raises(JournalRejected) as info:
        await gateway(capture(status, body)).ingest_deals("alice", REF, [ENTRY])
    assert info.value.details == [{"loc": ["x"]}]


async def test_timeouts_and_connection_errors_are_unavailable():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(JournalUnavailable):
        await gateway(httpx.MockTransport(boom)).ingest_deals("alice", REF, [ENTRY])

    unreachable = JournalHttpGateway("http://127.0.0.1:9", SERVICE_KEY, timeout=1.0)
    with pytest.raises(JournalUnavailable):
        await unreachable.ingest_deals("alice", REF, [ENTRY])


async def test_unusable_answer_is_unavailable():
    with pytest.raises(JournalUnavailable):
        await gateway(capture(200, {"success": True})).ingest_deals("alice", REF, [ENTRY])


async def test_skipped_positions_and_balance_events_are_returned_and_warned_without_secrets(caplog):
    body = {
        "success": True,
        "data": {
            "received": 2,
            "new": 2,
            "trades_upserted": 0,
            "balance_events": 3,
            "skipped": [{"position_id": "7", "reason": "reversal"}],
        },
    }
    with caplog.at_level(logging.WARNING):
        result = await gateway(capture(200, body)).ingest_deals("alice", REF, [ENTRY])
    assert result.balance_events == 3
    assert [(s.position_id, s.reason) for s in result.skipped] == [("7", "reversal")]
    assert "skipped 1 positions" in caplog.text
    assert "('7', 'reversal')" in caplog.text
    assert SERVICE_KEY not in caplog.text


async def test_no_warning_when_nothing_was_skipped(caplog):
    with caplog.at_level(logging.WARNING):
        await gateway(capture(200, OK_BODY)).ingest_deals("alice", REF, [ENTRY])
    assert "skipped" not in caplog.text


async def test_rejected_batch_logs_ticket_range_only(caplog):
    with caplog.at_level(logging.WARNING):
        with pytest.raises(JournalRejected):
            await gateway(
                capture(422, {"error": {"details": [{"secret": "payload-detail"}]}})
            ).ingest_deals("alice", REF, [ENTRY, EXIT])
    assert "tickets 1..2" in caplog.text
    assert "2 deals" in caplog.text
    assert "payload-detail" not in caplog.text
