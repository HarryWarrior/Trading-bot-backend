"""HTTP tests for the mt5 API: FakeTerminal, fake journal gateway, in-memory repository."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from mt5_fakes import (
    FakeJournalGateway,
    FakeTerminal,
    candle,
    closed_position_deals,
    terminal_account,
)
from pydantic import ValidationError

from mt5_service.main import create_app
from mt5_service.settings import Mt5Settings

SECRET = "test-secret-key-with-enough-length-0123456789"
SERVICE_KEY = "test-ingest-service-key-with-enough-length-0123456789"
BASE = "/api/v1/mt5"
RATES = f"{BASE}/rates?symbol=EURUSD&timeframe=H1"


def token_for(user_id: str = "alice", role: str = "admin") -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "email": f"{user_id}@mail.com",
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(claims, SECRET, algorithm="HS256")


def auth(user_id: str = "alice", role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user_id, role)}"}


def make_settings(**overrides) -> Mt5Settings:
    values = dict(
        _env_file=None,
        environment="test",
        jwt_secret_key=SECRET,
        ingest_service_key=SERVICE_KEY,
    )
    values.update(overrides)
    return Mt5Settings(**values)


@pytest.fixture
def client(terminal: FakeTerminal, journal: FakeJournalGateway, repo, clock) -> TestClient:
    app = create_app(
        make_settings(), terminal=terminal, journal=journal, accounts=repo, clock=clock
    )
    return TestClient(app)


def link(client: TestClient, user_id: str = "alice"):
    return client.post(f"{BASE}/accounts/link", headers=auth(user_id))


def test_requires_authentication(client):
    assert client.get(f"{BASE}/accounts").status_code == 401
    assert client.get(f"{RATES}&count=1").status_code == 401


def test_non_admin_cannot_link_sync_or_unlink(client):
    user = auth("bob", "user")
    assert client.post(f"{BASE}/accounts/x/sync", headers=user).status_code == 403
    assert client.delete(f"{BASE}/accounts/x", headers=user).status_code == 403
    response = client.post(f"{BASE}/accounts/link", headers=user)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_link_unavailable_terminal_is_409(client, terminal):
    terminal.account = None
    response = link(client)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TERMINAL_NOT_AVAILABLE"


def test_link_is_created_then_idempotent(client):
    first = link(client)
    assert first.status_code == 201
    account = first.json()["data"]["account"]
    assert account["account_ref"] == "123456@Demo-Server"
    assert account["login"] == 123456
    assert account["trade_mode"] == "demo"
    assert account["last_sync_at"] is None and account["last_sync_result"] is None
    again = link(client)
    assert again.status_code == 200
    assert again.json()["data"]["account"]["id"] == account["id"]


def test_other_admin_cannot_link_same_account(client):
    assert link(client, "alice").status_code == 201
    response = link(client, "carol")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ACCOUNT_ALREADY_LINKED"


def test_sync_ok_returns_counts_and_forwards_token(client, terminal, journal):
    terminal.deals = closed_position_deals()
    account_id = link(client).json()["data"]["account"]["id"]
    response = client.post(f"{BASE}/accounts/{account_id}/sync", headers=auth())
    assert response.status_code == 200
    assert response.json()["data"]["result"] == {
        "created": 1,
        "updated": 0,
        "balance_events": 0,
        "open_positions": 0,
        "skipped_positions": 0,
    }
    assert len(journal.calls) == 1
    assert journal.calls[0][1] == "123456@Demo-Server"
    assert jwt.decode(journal.calls[0][0], SECRET, algorithms=["HS256"])["sub"] == "alice"
    listed = client.get(f"{BASE}/accounts", headers=auth()).json()["data"]["accounts"]
    assert listed[0]["last_sync_result"]["created"] == 1
    assert listed[0]["last_sync_at"] is not None


def test_sync_after_terminal_switched_is_409_and_journal_untouched(client, terminal, journal):
    account_id = link(client).json()["data"]["account"]["id"]
    terminal.account = terminal_account(login=999, server="Other")
    response = client.post(f"{BASE}/accounts/{account_id}/sync", headers=auth())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TERMINAL_ACCOUNT_MISMATCH"
    assert journal.calls == []


def test_sync_terminal_closed_is_409(client, terminal, journal):
    account_id = link(client).json()["data"]["account"]["id"]
    terminal.account = None
    response = client.post(f"{BASE}/accounts/{account_id}/sync", headers=auth())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TERMINAL_NOT_AVAILABLE"
    assert journal.calls == []


def test_sync_journal_down_is_503(client, journal):
    account_id = link(client).json()["data"]["account"]["id"]
    journal.unavailable = True
    response = client.post(f"{BASE}/accounts/{account_id}/sync", headers=auth())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "JOURNAL_UNAVAILABLE"


def test_status_connected_uses_live_terminal_values(client):
    account_id = link(client).json()["data"]["account"]["id"]
    response = client.get(f"{BASE}/accounts/{account_id}/status", headers=auth())
    status = response.json()["data"]["status"]
    assert status["connected"] is True
    assert status["balance"] == 10000.0
    assert status["equity"] == 10050.25
    assert status["as_of"] is not None


def test_status_disconnected_has_nulls(client, terminal):
    account_id = link(client).json()["data"]["account"]["id"]
    terminal.account = None
    response = client.get(f"{BASE}/accounts/{account_id}/status", headers=auth())
    assert response.json()["data"]["status"] == {
        "connected": False,
        "balance": None,
        "equity": None,
        "as_of": None,
        "last_sync_at": None,
    }


def test_users_are_isolated(client):
    account_id = link(client, "alice").json()["data"]["account"]["id"]
    other = auth("bob", "user")
    assert client.get(f"{BASE}/accounts", headers=other).json()["data"]["accounts"] == []
    assert client.get(f"{BASE}/accounts/{account_id}/status", headers=other).status_code == 404
    admin_b = auth("dave", "admin")
    assert client.post(f"{BASE}/accounts/{account_id}/sync", headers=admin_b).status_code == 404
    assert client.delete(f"{BASE}/accounts/{account_id}", headers=admin_b).status_code == 404


def test_unlink(client):
    account_id = link(client).json()["data"]["account"]["id"]
    assert client.delete(f"{BASE}/accounts/{account_id}", headers=auth()).status_code == 200
    assert client.get(f"{BASE}/accounts", headers=auth()).json()["data"]["accounts"] == []
    assert client.delete(f"{BASE}/accounts/{account_id}", headers=auth()).status_code == 404


def test_rates_returns_utc_candles_with_detected_offset(client, terminal):
    terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00", "1.10555")]
    response = client.get(f"{RATES}&count=5", headers=auth("bob", "user"))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["symbol"] == "EURUSD" and data["timeframe"] == "H1"
    first = data["candles"][0]
    assert first["time"].startswith("2026-03-02T12:00:00")  # server +3h -> UTC
    assert first["close"] == 1.10555  # prices are not rounded
    assert first["tick_volume"] == 10


def test_rates_errors(client, terminal):
    terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00")]
    h = auth("bob", "user")
    bad_tf = client.get(f"{BASE}/rates?symbol=EURUSD&timeframe=H2&count=5", headers=h)
    assert bad_tf.status_code == 422
    assert bad_tf.json()["error"]["code"] == "INVALID_TIMEFRAME"
    unknown = client.get(f"{BASE}/rates?symbol=NOPE&timeframe=H1&count=5", headers=h)
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "SYMBOL_NOT_FOUND"
    assert client.get(f"{RATES}&count=1001", headers=h).status_code == 422
    assert client.get(f"{RATES}&count=0", headers=h).status_code == 422
    assert client.get(f"{BASE}/rates?timeframe=H1&count=5", headers=h).status_code == 422
    terminal.account = None
    closed = client.get(f"{RATES}&count=5", headers=h)
    assert closed.status_code == 409
    assert closed.json()["error"]["code"] == "TERMINAL_NOT_AVAILABLE"


def test_server_utc_offset_setting_overrides_detection(terminal, journal, repo, clock):
    terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00")]
    settings = make_settings(server_utc_offset_minutes=120)
    app = create_app(settings, terminal=terminal, journal=journal, accounts=repo, clock=clock)
    client = TestClient(app)
    data = client.get(f"{RATES}&count=1", headers=auth()).json()["data"]
    assert data["candles"][0]["time"].startswith("2026-03-02T13:00:00")


def test_link_ignores_body_and_schema_has_no_credential_fields(client):
    response = client.post(
        f"{BASE}/accounts/link", headers=auth(), json={"password": "hunter2", "login": 1}
    )
    assert response.status_code == 201
    assert response.json()["data"]["account"]["login"] == 123456
    schema = json.dumps(client.get("/openapi.json").json()).lower()
    for word in ("password", "passwd", "secret", "credential", "investor"):
        assert word not in schema


def test_settings_validation():
    with pytest.raises(ValidationError):
        make_settings(jwt_secret_key="short")
    with pytest.raises(ValidationError):
        make_settings(ingest_service_key="short")
    with pytest.raises(ValidationError):
        make_settings(server_utc_offset_minutes=900)
    with pytest.raises(ValidationError):
        make_settings(server_utc_offset_minutes=-721)
    assert make_settings(server_utc_offset_minutes=180).server_utc_offset_minutes == 180
    assert make_settings().server_utc_offset_minutes is None
    assert make_settings().database_name == "mt5_db"


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "mt5"}


def test_offset_is_read_from_the_prefixed_env_var(monkeypatch):
    monkeypatch.setenv("MT5_SERVER_UTC_OFFSET_MINUTES", "120")
    assert make_settings().server_utc_offset_minutes == 120
