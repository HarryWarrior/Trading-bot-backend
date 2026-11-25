"""The gateway against the REAL journal app (throwaway DB) through an ASGI transport."""

from __future__ import annotations

import json
import logging
import uuid
import warnings
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import jwt
import pytest
from pymongo import MongoClient

# starlette 0.27 imports the legacy `multipart` alias, which python-multipart >= 0.0.13 flags.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", PendingDeprecationWarning)
    import multipart  # noqa: F401

from journal_service.main import create_app as create_journal_app
from journal_service.settings import JournalSettings
from mt5_service.adapters.outbound.journal_gateway import JournalHttpGateway
from mt5_service.domain.errors import JournalUnavailable, Unauthenticated
from mt5_service.domain.trades import BalanceEventOut, TradeOut

MONGO_URL = "mongodb://localhost:27017"
SECRET = "test-secret-key-with-enough-length-0123456789"
SERVICE_KEY = "test-ingest-service-key-with-enough-length-0123456789"
REF = "123456@Demo-Server"


def token(user_id: str = "u1", secret: str = SECRET) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "email": f"{user_id}@mail.com",
        "role": "admin",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def trade() -> TradeOut:
    return TradeOut(
        position_id="7",
        symbol="EURUSD",
        side="buy",
        volume=Decimal("1.0"),
        open_time=datetime(2026, 3, 2, 7, 0, tzinfo=UTC),
        close_time=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
        open_price=Decimal("1.1000"),
        close_price=Decimal("1.1050"),
        commission=Decimal("-4"),
        swap=Decimal("0"),
        profit=Decimal("50"),
        comment="c",
    )


def deposit() -> BalanceEventOut:
    return BalanceEventOut("deposit", Decimal("1000"), datetime(2026, 3, 1, tzinfo=UTC), "d1")


@pytest.fixture
def database_name():
    sync_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=1000)
    try:
        sync_client.admin.command("ping")
    except Exception:
        sync_client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    name = f"test_mt5_journal_{uuid.uuid4().hex}"
    try:
        yield name
    finally:
        sync_client.drop_database(name)
        sync_client.close()


@pytest.fixture
async def stack(database_name):
    """ASGI transport of the real journal app, lifespan entered in this event loop."""
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
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        yield transport


async def dataset(transport, user_id: str = "u1") -> dict:
    async with httpx.AsyncClient(transport=transport, base_url="http://journal.test") as client:
        response = await client.get(
            "/api/v1/journal/dataset",
            params={"account_ref": REF},
            headers={"Authorization": f"Bearer {token(user_id)}"},
        )
    return response.json()["data"]


def gateway(transport, key: str = SERVICE_KEY) -> JournalHttpGateway:
    return JournalHttpGateway("http://journal.test", key, transport=transport)


async def test_ingest_lands_trades_and_second_ingest_creates_nothing(stack):
    gw = gateway(stack)
    first = await gw.ingest(token(), REF, [trade()], [deposit()])
    assert (first.created, first.updated, first.balance_events) == (1, 0, 1)
    second = await gw.ingest(token(), REF, [trade()], [deposit()])
    assert (second.created, second.updated, second.balance_events) == (0, 1, 0)

    data = await dataset(stack)
    assert len(data["trades"]) == 1
    assert data["trades"][0]["source"] == "mt5"
    assert data["trades"][0]["net"] == 46.0
    assert len(data["balance_events"]) == 1
    assert await dataset(stack, "other") == {"trades": [], "balance_events": []}


async def test_wrong_service_key_is_journal_unavailable_and_logged(stack, caplog):
    with caplog.at_level(logging.WARNING):
        with pytest.raises(JournalUnavailable):
            await gateway(stack, key="x" * 40).ingest(token(), REF, [trade()], [])
    assert "journal rejected service key" in caplog.text.lower()
    assert SERVICE_KEY not in caplog.text
    assert await dataset(stack) == {"trades": [], "balance_events": []}


async def test_bad_token_is_unauthenticated(stack):
    with pytest.raises(Unauthenticated):
        await gateway(stack).ingest(token(secret="y" * 40), REF, [trade()], [])


async def test_connection_error_is_journal_unavailable():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    gw = JournalHttpGateway("http://journal.test", SERVICE_KEY, transport=httpx.MockTransport(boom))
    with pytest.raises(JournalUnavailable):
        await gw.ingest("t", REF, [trade()], [])


async def test_server_error_and_garbage_are_journal_unavailable(caplog):
    for response in (httpx.Response(500, text="x"), httpx.Response(200, text="not json")):
        gw = JournalHttpGateway(
            "http://journal.test",
            SERVICE_KEY,
            transport=httpx.MockTransport(lambda request, r=response: r),
        )
        with pytest.raises(JournalUnavailable):
            await gw.ingest("secret-token-value", REF, [], [])
    assert "secret-token-value" not in caplog.text


async def test_request_shape_and_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json={"data": {"created": 2, "updated": 1, "balance_events": 3}})

    gw = JournalHttpGateway(
        "http://journal.test/", SERVICE_KEY, transport=httpx.MockTransport(handler)
    )
    result = await gw.ingest("tok", REF, [trade()], [deposit()])
    request = seen["request"]
    assert (result.created, result.updated, result.balance_events) == (2, 1, 3)
    assert request.url.path == "/api/v1/journal/ingest/mt5"
    assert request.headers["authorization"] == "Bearer tok"
    assert request.headers["x-service-key"] == SERVICE_KEY
    body = json.loads(request.content)
    assert body["account_ref"] == REF
    assert body["trades"] == [trade().to_payload()]
    assert body["balance_events"] == [deposit().to_payload()]
