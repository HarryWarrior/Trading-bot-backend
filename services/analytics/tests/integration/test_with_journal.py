"""End to end without ports: the real journal app (throwaway Mongo DB) behind an ASGI transport.

The journal lifespan (indexes, Mongo close) is entered with ``router.lifespan_context`` so both
apps share one event loop; analytics reaches journal through ``httpx.ASGITransport`` and no
network port is opened. No extra dependency (such as asgi-lifespan) is needed.
"""

from __future__ import annotations

import uuid
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import jwt
import pytest
from pymongo import MongoClient

# starlette 0.27 imports the legacy `multipart` alias, which python-multipart >= 0.0.13 flags.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", PendingDeprecationWarning)
    import multipart  # noqa: F401

from analytics_service.adapters.outbound.journal_client import JournalHttpTradeSource
from analytics_service.main import create_app
from analytics_service.settings import AnalyticsSettings
from journal_service.main import create_app as create_journal_app
from journal_service.settings import JournalSettings

MONGO_URL = "mongodb://localhost:27017"
SECRET = "test-secret-key-with-enough-length-0123456789"
SAMPLE = Path(__file__).resolve().parents[4] / "data" / "samples" / "sample_trades.csv"


def auth(user_id: str) -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "email": f"{user_id}@mail.com",
        "role": "user",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return {"Authorization": "Bearer " + jwt.encode(claims, SECRET, algorithm="HS256")}


@pytest.fixture
def database_name():
    sync_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=1000)
    try:
        sync_client.admin.command("ping")
    except Exception:
        sync_client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    name = f"test_journal_{uuid.uuid4().hex}"
    try:
        yield name
    finally:
        sync_client.drop_database(name)
        sync_client.close()


@pytest.fixture
async def stack(database_name):
    """Journal and analytics in ONE event loop (Motor binds to the loop that first uses it)."""
    journal_app = create_journal_app(
        JournalSettings(
            _env_file=None,
            environment="test",
            database_name=database_name,
            mongodb_url=MONGO_URL,
            jwt_secret_key=SECRET,
            ingest_service_key="test-ingest-service-key-with-enough-length-0123456789",
        )
    )
    transport = httpx.ASGITransport(app=journal_app)
    source = JournalHttpTradeSource("http://journal.test", transport=transport)
    analytics_app = create_app(
        AnalyticsSettings(_env_file=None, environment="test", jwt_secret_key=SECRET),
        trade_source=source,
    )
    async with journal_app.router.lifespan_context(journal_app):
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://journal.test") as journal,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=analytics_app), base_url="http://analytics.test"
            ) as analytics,
        ):
            yield journal, analytics


async def test_users_get_only_their_own_kpis(stack):
    journal, analytics = stack
    uploaded = await journal.post(
        "/api/v1/journal/imports",
        files={"file": ("sample_trades.csv", SAMPLE.read_bytes(), "text/csv")},
        headers=auth("alice"),
    )
    assert uploaded.status_code == 201

    alice = await analytics.get("/api/v1/analytics/summary", headers=auth("alice"))
    assert alice.status_code == 200
    summary = alice.json()["data"]["summary"]
    assert summary["net_profit"] == 1450.00
    assert summary["win_rate"] == 70.00

    bob = await analytics.get("/api/v1/analytics/summary", headers=auth("bob"))
    assert bob.status_code == 200
    assert bob.json()["data"]["summary"]["total_trades"] == 0

    equity = await analytics.get("/api/v1/analytics/equity", headers=auth("alice"))
    assert len(equity.json()["data"]["points"]) == summary["total_trades"]
