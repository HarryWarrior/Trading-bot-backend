"""HTTP tests for the bridge API with in-memory repositories and a fake journal gateway."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from mt5_bridge_service.domain.errors import JournalRejected, JournalUnavailable
from mt5_bridge_service.main import create_app
from mt5_bridge_service.settings import BridgeSettings

SECRET = "test-secret-key-with-enough-length-0123456789"
SERVICE_KEY = "test-ingest-service-key-with-enough-length-0123456789"
BASE = "/api/v1/mt5-bridge"


def auth(user_id: str = "alice", role: str = "user") -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "email": f"{user_id}@mail.com",
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, SECRET, algorithm='HS256')}"}


def bearer(plaintext: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {plaintext}"}


def make_settings(**overrides) -> BridgeSettings:
    values = dict(
        _env_file=None,
        environment="test",
        jwt_secret_key=SECRET,
        ingest_service_key=SERVICE_KEY,
    )
    values.update(overrides)
    return BridgeSettings(**values)


@pytest.fixture
def ea_file(tmp_path):
    return tmp_path / "TradingJournalBridge.ex5"


@pytest.fixture
def client(tokens, accounts, journal, clock, ea_file) -> TestClient:
    app = create_app(
        make_settings(ea_file_path=ea_file),
        journal=journal,
        tokens=tokens,
        accounts=accounts,
        clock=clock,
    )
    return TestClient(app)


def raw(ticket: int, time: str = "2026-03-02T08:00:00Z", **extra) -> dict:
    base = {
        "ticket": ticket,
        "position_id": 7,
        "time": time,
        "type": 0,
        "entry": 0,
        "symbol": "EURUSD",
        "volume": "1.0",
        "price": "1.1",
        "commission": "-1",
        "swap": "0",
        "profit": "0",
    }
    base.update(extra)
    return base


def deals_body(deals: list[dict], login: int = 123456, server: str = "Demo-Server") -> dict:
    return {"account_login": login, "server": server, "deals": deals}


def heartbeat_body(login: int = 123456, server: str = "Demo-Server") -> dict:
    return {
        "account_login": login,
        "server": server,
        "balance": "1000.456",
        "equity": "990.1",
        "terminal_build": 4755,
    }


def issue(client: TestClient, user_id: str = "alice", name: str = "Laptop EA") -> dict:
    response = client.post(f"{BASE}/tokens", json={"name": name}, headers=auth(user_id))
    assert response.status_code == 201, response.text
    return response.json()["data"]


# --- tokens (JWT) ---------------------------------------------------------------------------


def test_user_endpoints_require_jwt(client):
    for method, path in [
        ("post", "/tokens"),
        ("get", "/tokens"),
        ("delete", "/tokens/x"),
        ("get", "/accounts"),
        ("get", "/ea/download"),
    ]:
        response = getattr(client, method)(f"{BASE}{path}")
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_ingest_token_is_not_a_jwt(client):
    plaintext = issue(client)["plaintext_token"]
    response = client.get(f"{BASE}/tokens", headers=bearer(plaintext))
    assert response.status_code == 401


def test_create_token_response_contains_plaintext_but_list_does_not(client):
    created = issue(client)
    plaintext = created["plaintext_token"]
    assert len(plaintext) >= 43  # 32 random bytes, URL-safe base64
    assert created["token"]["name"] == "Laptop EA"
    assert created["token"]["scope"] == "ingest:mt5"
    assert created["token"]["active"] is True
    assert "hash" not in created["token"]

    response = client.get(f"{BASE}/tokens", headers=auth())
    assert response.status_code == 200
    body = response.text
    assert plaintext not in body
    assert "hash" not in body
    [listed] = response.json()["data"]["items"]
    assert listed["id"] == created["token"]["id"]
    assert "plaintext_token" not in listed


def test_blank_token_name_is_400(client):
    response = client.post(f"{BASE}/tokens", json={"name": "   "}, headers=auth())
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_TOKEN_NAME"


def test_revoke_token_then_it_no_longer_authenticates(client, journal):
    created = issue(client)
    token_id, plaintext = created["token"]["id"], created["plaintext_token"]
    response = client.delete(f"{BASE}/tokens/{token_id}", headers=auth())
    assert response.status_code == 200
    assert response.json()["data"]["token"]["active"] is False
    assert response.json()["data"]["token"]["revoked_at"] is not None

    response = client.post(
        f"{BASE}/ingest/deals", json=deals_body([raw(1)]), headers=bearer(plaintext)
    )
    assert response.status_code == 401
    assert journal.calls == []


def test_revoke_unknown_or_foreign_token_is_404(client):
    created = issue(client, "alice")
    for user in ("alice", "bob"):
        target = "missing" if user == "alice" else created["token"]["id"]
        response = client.delete(f"{BASE}/tokens/{target}", headers=auth(user))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
    assert client.get(f"{BASE}/tokens", headers=auth("alice")).json()["data"]["items"][0]["active"]


# --- EA ingest (ingest token) ---------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer "}, {"Authorization": "Basic abc"}, bearer("unknown-token")],
)
def test_unknown_or_revoked_token_returns_401_and_stores_nothing(
    client, journal, accounts, tokens, headers
):
    issue(client)
    for path, body in [("deals", deals_body([raw(1)])), ("heartbeat", heartbeat_body())]:
        response = client.post(f"{BASE}/ingest/{path}", json=body, headers=headers)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert journal.calls == []
    assert accounts.rows == {}
    assert all(t.last_used_at is None for t in tokens.rows.values())


def test_token_updates_last_used_at(client, tokens, clock):
    created = issue(client)
    assert created["token"]["last_used_at"] is None
    clock.advance(timedelta(minutes=7))
    response = client.post(
        f"{BASE}/ingest/heartbeat",
        json=heartbeat_body(),
        headers=bearer(created["plaintext_token"]),
    )
    assert response.status_code == 200
    [listed] = client.get(f"{BASE}/tokens", headers=auth()).json()["data"]["items"]
    assert listed["last_used_at"] == "2026-01-01T12:07:00Z"


def test_deals_forwarded_with_token_owner_user_id(client, journal):
    plaintext = issue(client, "alice")["plaintext_token"]
    body = deals_body(
        [raw(1, "2026-03-02T10:00:00+02:00"), raw(2, sl="1.09", tp="1.2", comment="x")]
    )
    body["user_id"] = "bob"  # ignored: the owner comes from the token only
    response = client.post(f"{BASE}/ingest/deals", json=body, headers=bearer(plaintext))
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"received": 2, "new": 2, "trades_upserted": 1}

    [(user_id, account_ref, deals)] = journal.calls
    assert (user_id, account_ref) == ("alice", "123456@Demo-Server")
    assert deals[0].time == datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    assert deals[0].time.utcoffset() == timedelta(0)
    assert str(deals[1].sl) == "1.09"


def test_deals_update_last_deal_at_of_the_account(client, clock):
    plaintext = issue(client)["plaintext_token"]
    client.post(f"{BASE}/ingest/heartbeat", json=heartbeat_body(), headers=bearer(plaintext))
    client.post(
        f"{BASE}/ingest/deals",
        json=deals_body([raw(1, "2026-03-02T08:00:00Z"), raw(2, "2026-03-02T09:30:00Z")]),
        headers=bearer(plaintext),
    )
    [account] = client.get(f"{BASE}/accounts", headers=auth()).json()["data"]["items"]
    assert account["last_deal_at"] == "2026-03-02T09:30:00Z"


def test_naive_deal_time_is_422(client, journal):
    plaintext = issue(client)["plaintext_token"]
    response = client.post(
        f"{BASE}/ingest/deals",
        json=deals_body([raw(1, "2026-03-02T08:00:00")]),
        headers=bearer(plaintext),
    )
    assert response.status_code == 422
    assert journal.calls == []


def test_zero_volume_trade_deal_is_422(client, journal):
    plaintext = issue(client)["plaintext_token"]
    response = client.post(
        f"{BASE}/ingest/deals", json=deals_body([raw(1, volume="0")]), headers=bearer(plaintext)
    )
    assert response.status_code == 422
    assert journal.calls == []


def test_batches_are_capped_at_200_deals(client, journal):
    plaintext = issue(client)["plaintext_token"]
    ok = client.post(
        f"{BASE}/ingest/deals",
        json=deals_body([raw(i) for i in range(200)]),
        headers=bearer(plaintext),
    )
    assert ok.status_code == 200
    too_many = client.post(
        f"{BASE}/ingest/deals",
        json=deals_body([raw(i) for i in range(201)]),
        headers=bearer(plaintext),
    )
    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] == "VALIDATION_ERROR"
    assert len(journal.calls) == 1


def test_journal_down_returns_503(client, journal):
    plaintext = issue(client)["plaintext_token"]
    journal.error = JournalUnavailable("Journal is unreachable")
    response = client.post(
        f"{BASE}/ingest/deals", json=deals_body([raw(1)]), headers=bearer(plaintext)
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "JOURNAL_UNAVAILABLE"


def test_journal_rejection_is_422_so_the_ea_does_not_retry_forever(client, journal):
    plaintext = issue(client)["plaintext_token"]
    journal.error = JournalRejected(details=[{"loc": ["body", "deals", 0], "msg": "bad"}])
    response = client.post(
        f"{BASE}/ingest/deals", json=deals_body([raw(1)]), headers=bearer(plaintext)
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "JOURNAL_REJECTED"
    assert error["details"] == [{"loc": ["body", "deals", 0], "msg": "bad"}]


def test_heartbeat_upserts_account_and_lists_status(client, clock):
    plaintext = issue(client)["plaintext_token"]
    for _ in range(2):
        response = client.post(
            f"{BASE}/ingest/heartbeat", json=heartbeat_body(), headers=bearer(plaintext)
        )
        assert response.status_code == 200
    assert response.json()["data"]["account"]["account_ref"] == "123456@Demo-Server"

    [account] = client.get(f"{BASE}/accounts", headers=auth()).json()["data"]["items"]
    assert account == {
        "account_ref": "123456@Demo-Server",
        "login": 123456,
        "server": "Demo-Server",
        "balance": 1000.46,
        "equity": 990.1,
        "terminal_build": 4755,
        "last_heartbeat": "2026-01-01T12:00:00Z",
        "last_deal_at": None,
        "status": "connected",
    }
    clock.advance(timedelta(minutes=6))
    [account] = client.get(f"{BASE}/accounts", headers=auth()).json()["data"]["items"]
    assert account["status"] == "disconnected"


def test_invalid_heartbeat_is_422(client, accounts):
    plaintext = issue(client)["plaintext_token"]
    response = client.post(
        f"{BASE}/ingest/heartbeat",
        json=heartbeat_body(login=0),
        headers=bearer(plaintext),
    )
    assert response.status_code == 422
    assert accounts.rows == {}


def test_token_of_user_a_never_lists_or_writes_user_b(client, journal):
    alice = issue(client, "alice")["plaintext_token"]
    bob = issue(client, "bob")["plaintext_token"]
    client.post(f"{BASE}/ingest/heartbeat", json=heartbeat_body(), headers=bearer(alice))
    client.post(f"{BASE}/ingest/deals", json=deals_body([raw(1)]), headers=bearer(alice))

    assert client.get(f"{BASE}/accounts", headers=auth("bob")).json()["data"]["items"] == []
    bob_tokens = client.get(f"{BASE}/tokens", headers=auth("bob")).json()["data"]["items"]
    assert [t["name"] for t in bob_tokens] == ["Laptop EA"]
    alice_tokens = client.get(f"{BASE}/tokens", headers=auth("alice")).json()["data"]["items"]
    assert {t["id"] for t in alice_tokens}.isdisjoint({t["id"] for t in bob_tokens})
    assert [user for user, _, _ in journal.calls] == ["alice"]

    client.post(f"{BASE}/ingest/heartbeat", json=heartbeat_body(), headers=bearer(bob))
    [alice_acc] = client.get(f"{BASE}/accounts", headers=auth("alice")).json()["data"]["items"]
    [bob_acc] = client.get(f"{BASE}/accounts", headers=auth("bob")).json()["data"]["items"]
    assert alice_acc["account_ref"] == bob_acc["account_ref"] == "123456@Demo-Server"


def test_plaintext_token_never_in_logs(client, journal, caplog):
    with caplog.at_level(logging.DEBUG):
        plaintext = issue(client)["plaintext_token"]
        client.get(f"{BASE}/tokens", headers=auth())
        client.post(f"{BASE}/ingest/heartbeat", json=heartbeat_body(), headers=bearer(plaintext))
        client.post(f"{BASE}/ingest/deals", json=deals_body([raw(1)]), headers=bearer(plaintext))
        journal.error = JournalUnavailable()
        client.post(f"{BASE}/ingest/deals", json=deals_body([raw(2)]), headers=bearer(plaintext))
        client.post(f"{BASE}/ingest/deals", json={"bad": 1}, headers=bearer(plaintext))
        client.post(f"{BASE}/ingest/deals", json=deals_body([]), headers=bearer(plaintext + "x"))
    assert caplog.records  # the run did log something
    assert plaintext not in caplog.text
    assert SERVICE_KEY not in caplog.text


# --- EA download ----------------------------------------------------------------------------


def test_ea_download_is_404_until_built(client):
    response = client.get(f"{BASE}/ea/download", headers=auth())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_ea_download_serves_the_compiled_ea(client, ea_file):
    ea_file.write_bytes(b"EX5\x00binary")
    response = client.get(f"{BASE}/ea/download", headers=auth())
    assert response.status_code == 200
    assert response.content == b"EX5\x00binary"
    assert "TradingJournalBridge.ex5" in response.headers["content-disposition"]
    assert response.headers["content-type"] == "application/octet-stream"


def test_default_ea_path_points_at_the_service_ea_folder():
    path = make_settings().ea_file_path
    assert path.name == "TradingJournalBridge.ex5"
    assert path.parent.name == "ea"
    assert path.parent.parent.name == "mt5-bridge"


# --- pagination -----------------------------------------------------------------------------


def test_tokens_are_paginated_newest_first_and_never_leak_other_users(client, clock):
    for name in ("one", "two", "three"):
        issue(client, "alice", name)
        clock.advance(timedelta(minutes=1))
    issue(client, "bob", "bob's")

    first = client.get(f"{BASE}/tokens?page=1&page_size=2", headers=auth("alice")).json()["data"]
    assert [t["name"] for t in first["items"]] == ["three", "two"]
    assert first["pagination"] == {
        "page": 1,
        "page_size": 2,
        "total_items": 3,
        "total_pages": 2,
        "has_next": True,
        "has_prev": False,
    }
    second = client.get(f"{BASE}/tokens?page=2&page_size=2", headers=auth("alice")).json()["data"]
    assert [t["name"] for t in second["items"]] == ["one"]
    assert (second["pagination"]["has_next"], second["pagination"]["has_prev"]) == (False, True)
    beyond = client.get(f"{BASE}/tokens?page=3&page_size=2", headers=auth("alice")).json()["data"]
    assert beyond["items"] == []
    assert beyond["pagination"]["total_items"] == 3

    bob = client.get(f"{BASE}/tokens?page_size=100", headers=auth("bob")).json()["data"]
    assert [t["name"] for t in bob["items"]] == ["bob's"]
    assert bob["pagination"]["total_items"] == 1


def test_accounts_are_paginated_by_account_ref_and_never_leak_other_users(client):
    alice = issue(client, "alice")["plaintext_token"]
    bob = issue(client, "bob")["plaintext_token"]
    for login in (333, 111, 222):
        client.post(
            f"{BASE}/ingest/heartbeat", json=heartbeat_body(login=login), headers=bearer(alice)
        )
    client.post(f"{BASE}/ingest/heartbeat", json=heartbeat_body(login=999), headers=bearer(bob))

    first = client.get(f"{BASE}/accounts?page=1&page_size=2", headers=auth("alice")).json()["data"]
    assert [a["login"] for a in first["items"]] == [111, 222]
    assert first["pagination"]["total_items"] == 3
    assert first["pagination"]["has_next"] is True
    second = client.get(f"{BASE}/accounts?page=2&page_size=2", headers=auth("alice")).json()
    assert [a["login"] for a in second["data"]["items"]] == [333]

    bob_page = client.get(f"{BASE}/accounts", headers=auth("bob")).json()["data"]
    assert [a["login"] for a in bob_page["items"]] == [999]
    assert bob_page["pagination"]["total_items"] == 1


@pytest.mark.parametrize("query", ["page=0", "page_size=0", "page_size=101", "page=x"])
def test_invalid_page_params_are_422(client, query):
    for path in ("tokens", "accounts"):
        response = client.get(f"{BASE}/{path}?{query}", headers=auth())
        assert response.status_code == 422, (path, query)
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
