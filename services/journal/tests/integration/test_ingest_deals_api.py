"""HTTP + Mongo tests for the service-key raw-deal ingest endpoint."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from journal_service.main import create_app
from journal_service.settings import JournalSettings

MONGO_URL = "mongodb://localhost:27017"
SECRET = "test-secret-key-with-enough-length-0123456789"
SERVICE_KEY = "test-ingest-service-key-with-enough-length-0123456789"
BASE = "/api/v1/journal"
ACCOUNT = "123@Demo-Server"


def auth(user_id: str) -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "email": f"{user_id}@mail.com",
        "role": "user",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, SECRET, algorithm='HS256')}"}


KEY = {"X-Service-Key": SERVICE_KEY}


@pytest.fixture
def client():
    sync_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=1000)
    try:
        sync_client.admin.command("ping")
    except Exception:
        sync_client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    name = f"test_journal_deals_{uuid.uuid4().hex}"
    settings = JournalSettings(
        _env_file=None,
        environment="test",
        mongodb_url=MONGO_URL,
        database_name=name,
        jwt_secret_key=SECRET,
        ingest_service_key=SERVICE_KEY,
    )
    try:
        with TestClient(create_app(settings)) as test_client:
            yield test_client
    finally:
        sync_client.drop_database(name)
        sync_client.close()


def raw(ticket, position_id, time, type_, entry, **extra):
    base = {
        "ticket": ticket,
        "position_id": position_id,
        "time": time,
        "type": type_,
        "entry": entry,
        "symbol": "EURUSD",
        "volume": "1.0",
        "price": "1.1",
        "commission": "-1",
        "swap": "0",
        "profit": "0",
    }
    base.update(extra)
    return base


ENTRY = raw(1, 7, "2026-03-02T08:00:00Z", 0, 0, sl="1.09", tp="1.12", comment="go")
EXIT = raw(2, 7, "2026-03-02T09:00:00Z", 1, 1, price="1.2", profit="100", fee="-0.5")
DEPOSIT = raw(3, 0, "2026-03-02T07:00:00Z", 2, 0, volume="0", price="0", profit="500")


def body(deals, user_id="alice", account_ref=ACCOUNT):
    return {"user_id": user_id, "account_ref": account_ref, "deals": deals}


def post(client, payload, headers=KEY):
    return client.post(f"{BASE}/ingest/deals", json=payload, headers=headers)


def test_without_service_key_is_403(client):
    response = post(client, body([ENTRY, EXIT]), headers=auth("alice"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_wrong_service_key_is_403_before_the_body(client):
    response = post(client, {"bad": 1}, headers={"X-Service-Key": "x" * 40})
    assert response.status_code == 403


def test_with_key_creates_a_trade_visible_to_that_user_only(client):
    response = post(client, body([ENTRY, EXIT, DEPOSIT]))

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert (data["received"], data["new"], data["trades_upserted"]) == (3, 3, 1)
    assert data["balance_events"] == 1
    assert data["skipped"] == []

    dataset = client.get(f"{BASE}/dataset", headers=auth("alice")).json()["data"]
    [trade] = dataset["trades"]
    assert trade["position_id"] == "7"
    assert trade["account_ref"] == ACCOUNT
    assert trade["source"] == "mt5"
    assert trade["commission"] == -2.5
    assert trade["profit"] == 100
    assert (trade["stop_loss"], trade["take_profit"]) == (1.09, 1.12)
    assert trade["open_time"].startswith("2026-03-02T08:00:00")
    assert [e["amount"] for e in dataset["balance_events"]] == [500]

    other = client.get(f"{BASE}/dataset", headers=auth("bob")).json()["data"]
    assert other == {"trades": [], "balance_events": []}


def test_repeat_call_returns_new_zero(client):
    post(client, body([ENTRY, EXIT]))
    response = post(client, body([ENTRY, EXIT]))
    data = response.json()["data"]
    assert (data["new"], data["trades_upserted"]) == (0, 1)
    trades = client.get(f"{BASE}/dataset", headers=auth("alice")).json()["data"]["trades"]
    assert len(trades) == 1


def test_late_exit_in_a_second_call_completes_the_trade(client):
    first = post(client, body([ENTRY])).json()["data"]
    assert first["trades_upserted"] == 0
    second = post(client, body([EXIT])).json()["data"]
    assert second["trades_upserted"] == 1
    trades = client.get(f"{BASE}/dataset", headers=auth("alice")).json()["data"]["trades"]
    assert len(trades) == 1


def test_naive_times_are_rejected(client):
    response = post(client, body([raw(1, 7, "2026-03-02T08:00:00", 0, 0)]))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_user_id_is_required(client):
    response = post(client, {"account_ref": ACCOUNT, "deals": [ENTRY]})
    assert response.status_code == 422
