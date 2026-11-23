"""Acceptance: MT5 account management (`/api/v1/mt5`).

The legacy implementation simulates brokers when the MetaTrader5 package is absent.
Spec 002 replaces it with the EA bridge (ADR 0002); these tests document the gap.
"""

from datetime import datetime

import pytest

from tests.acceptance.conftest import known_bug

API = "/api/v1/mt5"
FAKE_ACCOUNT = {
    "account_name": "Acceptance fake",
    "login": 99887766,
    "password": "made-up-pass-123",  # the simulator rejects passwords containing "wrong"/"invalid"
    "server": "AcmeMarkets-Demo",  # neutral name: the simulator rejects names containing "unreachable"
}


@pytest.fixture()
def stored_account(db):
    """An account document inserted directly, pointing to a broker that does not exist."""
    result = db.mt5_accounts.insert_one(
        {
            "user_id": None,
            "account_name": "Unreachable",
            "login": 11223344,
            "server": "AcmeMarkets-Demo",  # neutral name: the simulator rejects names containing "unreachable"
            "broker_name": "Unreachable",
            "platform": "MT5",
            "encrypted_password": "",
            "is_connected": False,
            "is_active": False,
            "balance": 0.0,
            "equity": 0.0,
            "created_at": datetime.utcnow(),
        }
    )
    yield str(result.inserted_id)
    db.mt5_accounts.delete_one({"_id": result.inserted_id})


@pytest.fixture()
def cleanup_accounts(db):
    yield
    db.mt5_accounts.delete_many({"server": FAKE_ACCOUNT["server"]})


def test_list_accounts_responds(client):
    assert client.get(f"{API}/accounts").status_code == 200


def test_unknown_account_status_is_404(client):
    assert client.get(f"{API}/accounts/000000000000000000000000/status").status_code == 404


def test_obviously_invalid_login_is_rejected(client, cleanup_accounts):
    response = client.post(f"{API}/accounts", json={**FAKE_ACCOUNT, "login": 12})
    assert response.status_code == 400


@known_bug(
    "any account at a made-up broker is accepted as connected; the simulator only rejects names containing words like unreachable/invalid"
)
def test_fake_broker_credentials_are_rejected(client, cleanup_accounts):
    response = client.post(f"{API}/accounts", json=FAKE_ACCOUNT)
    assert 400 <= response.status_code < 500


@known_bug(
    "broker password is stored (XOR + base64, reversible); ADR 0002 forbids storing broker passwords"
)
def test_broker_password_is_not_stored(client, db, cleanup_accounts):
    client.post(f"{API}/accounts", json=FAKE_ACCOUNT)
    document = db.mt5_accounts.find_one({"server": FAKE_ACCOUNT["server"]}) or {}
    assert not document.get("encrypted_password")


@known_bug(
    "the same login+server can be registered several times (3 duplicates found in the local DB)"
)
def test_duplicate_account_is_rejected(client, cleanup_accounts):
    client.post(f"{API}/accounts", json=FAKE_ACCOUNT)
    assert client.post(f"{API}/accounts", json=FAKE_ACCOUNT).status_code == 409


@known_bug("MT5 endpoints are public and accounts have no owner (user_id is null)")
def test_accounts_require_authentication(client):
    assert client.get(f"{API}/accounts").status_code == 401


@known_bug("sync invents random deals and balance when the broker is unreachable")
def test_sync_never_invents_deals(client, stored_account):
    response = client.post(f"{API}/accounts/{stored_account}/sync")
    assert response.status_code >= 400 or response.json()["synced_deals_count"] == 0


@known_bug("synced deals are not persisted anywhere: sync only returns a count")
def test_synced_deals_reach_the_journal(client, db, stored_account):
    client.post(f"{API}/accounts/{stored_account}/sync")
    assert db.list_collection_names() and "trades" in db.list_collection_names()


@known_bug(
    "candles from /rates are random numbers, not market data (two identical requests differ)"
)
def test_rates_are_deterministic(client):
    params = {"symbol": "XAUUSD", "timeframe": "1h", "count": 20}
    first = client.get(f"{API}/rates", params=params).json()["candles"]
    second = client.get(f"{API}/rates", params=params).json()["candles"]
    assert [c["close"] for c in first] == [c["close"] for c in second]
