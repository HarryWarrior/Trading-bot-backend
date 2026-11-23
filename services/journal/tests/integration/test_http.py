"""HTTP integration tests against a throwaway MongoDB database and minted HS256 tokens."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo import MongoClient

from journal_service.main import create_app
from journal_service.settings import JournalSettings

MONGO_URL = "mongodb://localhost:27017"
SECRET = "test-secret-key-with-enough-length-0123456789"
BASE = "/api/v1/journal"
SAMPLE = Path(__file__).resolve().parents[4] / "data" / "samples" / "sample_trades.csv"


def token_for(user_id: str, secret: str = SECRET) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "email": f"{user_id}@mail.com",
        "role": "user",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def auth(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user_id)}"}


@pytest.fixture
def database_name():
    sync_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=1000)
    try:
        sync_client.admin.command("ping")
    except Exception:
        sync_client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    name = f"test_journal_http_{uuid.uuid4().hex}"
    try:
        yield name
    finally:
        sync_client.drop_database(name)
        sync_client.close()


@pytest.fixture
def settings(database_name) -> JournalSettings:
    return JournalSettings(
        _env_file=None,
        environment="test",
        mongodb_url=MONGO_URL,
        database_name=database_name,
        jwt_secret_key=SECRET,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def upload(client, user="alice", name="sample_trades.csv", content=None):
    data = SAMPLE.read_bytes() if content is None else content
    return client.post(
        f"{BASE}/imports", files={"file": (name, data, "text/csv")}, headers=auth(user)
    )


def ingest_body(account_ref="999@Demo"):
    return {
        "account_ref": account_ref,
        "trades": [
            {
                "position_id": "p1",
                "symbol": "EURUSD",
                "side": "buy",
                "volume": 0.1,
                "open_time": "2026-01-01T08:00:00Z",
                "close_time": "2026-01-01T09:00:00Z",
                "open_price": 1.1,
                "close_price": 1.101,
                "commission": -0.5,
                "swap": 0,
                "profit": 10,
            }
        ],
        "balance_events": [
            {
                "kind": "deposit",
                "amount": 1000,
                "time": "2026-01-01T00:00:00Z",
                "source_ref": "b1",
            }
        ],
    }


def test_settings_reject_short_secret():
    with pytest.raises(ValidationError):
        JournalSettings(_env_file=None, jwt_secret_key="short")


def test_health_is_public(client):
    assert client.get("/health").json()["service"] == "journal"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/imports"),
        ("get", "/trades"),
        ("get", "/trades/x"),
        ("get", "/accounts"),
        ("get", "/dataset"),
        ("post", "/imports"),
        ("post", "/ingest/mt5"),
    ],
)
def test_no_token_is_401(client, method, path):
    response = getattr(client, method)(f"{BASE}{path}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_token_signed_with_other_secret_is_401(client):
    headers = {"Authorization": f"Bearer {token_for('a', secret='x' * 40)}"}
    assert client.get(f"{BASE}/trades", headers=headers).status_code == 401


def test_upload_sample_then_duplicate(client):
    response = upload(client)
    assert response.status_code == 201
    body = response.json()["data"]["import"]
    assert body["trades_created"] == 10
    assert body["trades_updated"] == 0
    assert body["filename"] == "sample_trades.csv"
    assert body["account_ref"] == f"upload:{body['id']}"
    assert body["skipped_rows"] == []
    assert set(body) == {
        "id",
        "filename",
        "account_ref",
        "trades_created",
        "trades_updated",
        "balance_events",
        "skipped_rows",
        "created_at",
    }

    again = upload(client)
    assert again.status_code == 409
    error = again.json()["error"]
    assert error["code"] == "DUPLICATE_IMPORT"
    assert error["details"] == {"import_id": body["id"]}


def test_upload_rejects_unsupported_extension(client):
    response = upload(client, name="report.txt")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE"


def test_upload_extension_check_is_case_insensitive(client):
    assert upload(client, name="SAMPLE.CSV").status_code == 201


def test_upload_too_large(client):
    response = upload(client, content=b"a" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_upload_garbage_csv_is_unreadable(client):
    response = upload(client, name="junk.csv", content=b"hello\nthis is not a report\n")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "UNREADABLE_REPORT"
    assert error["details"]["reason"]


def test_list_imports_paginated_and_isolated(client):
    upload(client, "alice")
    listing = client.get(f"{BASE}/imports", headers=auth("alice")).json()["data"]
    assert listing["pagination"]["total_items"] == 1
    assert listing["items"][0]["filename"] == "sample_trades.csv"
    other = client.get(f"{BASE}/imports", headers=auth("bob")).json()["data"]
    assert other["items"] == []


def test_trades_list_filters_pagination_and_json_shape(client):
    upload(client)
    headers = auth("alice")
    page = client.get(f"{BASE}/trades", params={"page_size": 3}, headers=headers).json()["data"]
    assert page["pagination"]["total_items"] == 10
    assert len(page["items"]) == 3
    trade = page["items"][0]
    assert set(trade) == {
        "id",
        "account_ref",
        "position_id",
        "symbol",
        "side",
        "volume",
        "open_time",
        "close_time",
        "open_price",
        "close_price",
        "stop_loss",
        "take_profit",
        "commission",
        "swap",
        "profit",
        "net",
        "outcome",
        "duration_minutes",
        "comment",
        "source",
        "import_id",
    }
    assert isinstance(trade["profit"], float)
    assert isinstance(trade["volume"], float)

    eur = client.get(f"{BASE}/trades", params={"symbol": "eurusd"}, headers=headers).json()["data"]
    assert eur["pagination"]["total_items"] > 0
    assert {t["symbol"] for t in eur["items"]} == {"EURUSD"}

    wins = client.get(f"{BASE}/trades", params={"outcome": "win"}, headers=headers).json()["data"]
    assert wins["items"] and all(t["outcome"] == "win" for t in wins["items"])

    big = client.get(f"{BASE}/trades", params={"profit_min": 500}, headers=headers).json()["data"]
    assert big["items"] and all(t["net"] >= 500 for t in big["items"])

    ranged = client.get(
        f"{BASE}/trades",
        params={"date_from": "2025-01-16T00:00:00Z", "date_to": "2025-01-17T00:00:00Z"},
        headers=headers,
    ).json()["data"]
    assert ranged["items"]
    assert all(t["close_time"].startswith("2025-01-16") for t in ranged["items"])

    by_profit = client.get(
        f"{BASE}/trades", params={"sort_by": "profit", "sort_dir": "asc"}, headers=headers
    ).json()["data"]["items"]
    nets = [t["net"] for t in by_profit]
    assert nets == sorted(nets)


def test_sort_by_unknown_is_422(client):
    response = client.get(f"{BASE}/trades", params={"sort_by": "password"}, headers=auth("alice"))
    assert response.status_code == 422


def test_page_size_over_limit_is_422(client):
    response = client.get(f"{BASE}/trades", params={"page_size": 1000}, headers=auth("alice"))
    assert response.status_code == 422


def test_user_isolation_and_trade_detail(client):
    upload(client, "alice")
    first = client.get(f"{BASE}/trades", headers=auth("alice")).json()["data"]["items"][0]

    mine = client.get(f"{BASE}/trades/{first['id']}", headers=auth("alice"))
    assert mine.status_code == 200
    assert mine.json()["data"]["trade"]["id"] == first["id"]

    theirs = client.get(f"{BASE}/trades/{first['id']}", headers=auth("bob"))
    assert theirs.status_code == 404
    assert theirs.json()["error"]["code"] == "NOT_FOUND"
    assert client.get(f"{BASE}/trades/nope", headers=auth("alice")).status_code == 404

    bob = client.get(f"{BASE}/trades", headers=auth("bob")).json()["data"]
    assert bob["pagination"]["total_items"] == 0
    assert client.get(f"{BASE}/accounts", headers=auth("bob")).json()["data"]["items"] == []
    dataset = client.get(f"{BASE}/dataset", headers=auth("bob")).json()["data"]
    assert dataset == {"trades": [], "balance_events": []}


def test_accounts(client):
    upload(client)
    items = client.get(f"{BASE}/accounts", headers=auth("alice")).json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["trades"] == 10
    assert items[0]["account_ref"].startswith("upload:")
    assert items[0]["first_trade_at"] and items[0]["last_trade_at"]


def test_ingest_twice_then_dataset(client):
    headers = auth("alice")
    first = client.post(f"{BASE}/ingest/mt5", json=ingest_body(), headers=headers)
    assert first.status_code == 200
    assert first.json()["data"] == {"created": 1, "updated": 0, "balance_events": 1}
    second = client.post(f"{BASE}/ingest/mt5", json=ingest_body(), headers=headers)
    assert second.json()["data"] == {"created": 0, "updated": 1, "balance_events": 1}

    dataset = client.get(
        f"{BASE}/dataset", params={"account_ref": "999@Demo"}, headers=headers
    ).json()["data"]
    assert len(dataset["trades"]) == 1
    assert dataset["trades"][0]["source"] == "mt5"
    assert dataset["trades"][0]["net"] == 9.5
    event = dataset["balance_events"][0]
    assert set(event) == {"id", "account_ref", "kind", "amount", "time", "source_ref", "comment"}
    assert event["amount"] == 1000.0
    assert event["kind"] == "deposit"

    other = client.get(f"{BASE}/dataset", params={"account_ref": "other"}, headers=headers).json()[
        "data"
    ]
    assert other == {"trades": [], "balance_events": []}


def test_ingest_rejects_naive_times(client):
    body = ingest_body()
    body["trades"][0]["open_time"] = "2026-01-01T08:00:00"
    response = client.post(f"{BASE}/ingest/mt5", json=body, headers=auth("alice"))
    assert response.status_code == 422


def test_money_rounded_prices_not(client):
    body = ingest_body()
    body["trades"][0].update({"profit": 10.456, "commission": -0.004, "open_price": 1.123456})
    client.post(f"{BASE}/ingest/mt5", json=body, headers=auth("alice"))
    trade = client.get(f"{BASE}/dataset", headers=auth("alice")).json()["data"]["trades"][0]
    assert trade["profit"] == 10.46
    assert trade["commission"] == 0.0
    assert trade["open_price"] == 1.123456
