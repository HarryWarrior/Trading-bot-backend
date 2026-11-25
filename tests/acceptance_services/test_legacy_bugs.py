"""The 14 legacy known bugs (tests/acceptance/test_{auth,analytics,mt5}.py), now PASSING tests.

Each test keeps the correct behavior the legacy API lacked and runs it against the new services.
Dropped on purpose: OAuth providers (Google/GitHub), a non-goal of spec 001 (auth is e-mail and
password only).
"""

from __future__ import annotations

from mt5_fakes import deal, terminal_account

from mt5_service.domain.deals import DealEntry, DealType
from tests.acceptance_services.harness import ANALYTICS, AUTH, JOURNAL, MT5, PASSWORD, SAMPLE

# --- auth (3 legacy bugs: 2 rewritten, OAuth dropped) -------------------------------------------


async def test_sign_up_does_not_expose_verification_code(stack):
    email = stack.new_email()
    response = await stack.auth.post(
        f"{AUTH}/sign-up", json={"email": email, "password": PASSWORD, "name": "A"}
    )
    code = stack.sender.last_code(email)
    assert code not in response.text
    assert "verification_code" not in response.text


async def test_resend_verification_does_not_expose_code(stack):
    email = await stack.sign_up()
    response = await stack.auth.post(f"{AUTH}/resend-verification", json={"email": email})
    assert response.status_code == 200
    assert response.json()["data"] is None
    assert stack.sender.last_code(email) not in response.text
    unknown = await stack.auth.post(
        f"{AUTH}/resend-verification", json={"email": "nobody@acceptance-tests.com"}
    )
    # no account enumeration either: same body apart from the timestamp
    assert unknown.json()["message"] == response.json()["message"]
    assert unknown.json()["data"] is None


def test_oauth_providers_are_dropped():
    """Legacy bug 3 (OAuth Google/GitHub returned 501) is dropped: OAuth is a non-goal."""


# --- analytics (4 legacy bugs) ------------------------------------------------------------------


async def test_kpis_are_rounded_to_two_decimals(stack):
    session = await stack.register()
    await stack.upload(session, "sample_trades.csv", SAMPLE.read_bytes())
    summary = await stack.summary(session)
    assert summary["profit_factor"] == 5.83  # legacy leaked 5.833333333333333
    for value in summary.values():
        if isinstance(value, float):
            assert value == round(value, 2)


async def test_drawdown_percentage_is_bounded(stack):
    admin = await stack.register(admin=True)
    stack.terminal.deals = [
        deal(1, 0, "2026-03-01T09:00:00", DealType.BALANCE, DealEntry.IN, profit="1000"),
        deal(2, 5, "2026-03-02T09:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(3, 5, "2026-03-02T10:00:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.1",
             profit="10"),
        deal(4, 6, "2026-03-02T11:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(5, 6, "2026-03-02T12:00:00", DealType.SELL, DealEntry.OUT, volume="1", price="1.0",
             profit="-400"),
    ]  # fmt: skip
    link = await stack.mt5.post(f"{MT5}/accounts/link", headers=admin.headers)
    account_id = link.json()["data"]["account"]["id"]
    sync = await stack.mt5.post(f"{MT5}/accounts/{account_id}/sync", headers=admin.headers)
    assert sync.status_code == 200
    summary = await stack.summary(admin)
    assert summary["max_drawdown"] == -400.0
    assert -100.0 <= summary["max_drawdown_pct"] <= 0.0  # legacy showed -3817.3%


async def test_analytics_requires_authentication(stack):
    assert (await stack.analytics.get(f"{ANALYTICS}/summary")).status_code == 401
    bad = await stack.analytics.get(
        f"{ANALYTICS}/summary", headers={"Authorization": "Bearer invalid"}
    )
    assert bad.status_code == 401


async def test_users_do_not_see_each_others_uploads(stack):
    alice = await stack.register()
    bob = await stack.register()
    await stack.upload(alice, "sample_trades.csv", SAMPLE.read_bytes())
    assert (await stack.summary(bob))["total_trades"] == 0
    assert (await stack.journal.get(f"{JOURNAL}/trades", headers=bob.headers)).json()["data"][
        "items"
    ] == []


# --- mt5 (7 legacy bugs) ------------------------------------------------------------------------


async def test_fake_broker_credentials_cannot_be_linked(stack):
    """Nothing is accepted from the client: only the account the real terminal reports links."""
    admin = await stack.register(admin=True)
    stack.terminal.account = None  # no terminal -> no account, whatever the client claims
    response = await stack.mt5.post(
        f"{MT5}/accounts/link",
        json={"login": 99887766, "password": "made-up-pass-123", "server": "AcmeMarkets-Demo"},
        headers=admin.headers,
    )
    assert response.status_code == 409
    assert (await stack.mt5.get(f"{MT5}/accounts", headers=admin.headers)).json()["data"][
        "accounts"
    ] == []


async def test_broker_password_is_not_stored(stack):
    admin = await stack.register(admin=True)
    link = await stack.mt5.post(f"{MT5}/accounts/link", headers=admin.headers)
    assert link.status_code == 201
    assert "password" not in link.text
    documents = list(stack.mongo[stack.databases["mt5"]]["linked_accounts"].find()) or list(
        doc
        for name in stack.mongo[stack.databases["mt5"]].list_collection_names()
        for doc in stack.mongo[stack.databases["mt5"]][name].find()
    )
    assert documents
    assert not any("password" in key.lower() for doc in documents for key in doc)


async def test_duplicate_account_is_rejected(stack):
    alice = await stack.register(admin=True)
    mallory = await stack.register(admin=True)
    first = await stack.mt5.post(f"{MT5}/accounts/link", headers=alice.headers)
    again = await stack.mt5.post(f"{MT5}/accounts/link", headers=alice.headers)
    assert again.status_code == 200  # same owner: idempotent, no second record
    assert again.json()["data"]["account"]["id"] == first.json()["data"]["account"]["id"]
    stolen = await stack.mt5.post(f"{MT5}/accounts/link", headers=mallory.headers)
    assert stolen.status_code == 409
    assert stolen.json()["error"]["code"] == "ACCOUNT_ALREADY_LINKED"
    listed = await stack.mt5.get(f"{MT5}/accounts", headers=alice.headers)
    assert len(listed.json()["data"]["accounts"]) == 1


async def test_accounts_require_authentication_and_have_an_owner(stack):
    assert (await stack.mt5.get(f"{MT5}/accounts")).status_code == 401
    alice = await stack.register(admin=True)
    bob = await stack.register(admin=True)
    await stack.mt5.post(f"{MT5}/accounts/link", headers=alice.headers)
    mine = await stack.mt5.get(f"{MT5}/accounts", headers=alice.headers)
    theirs = await stack.mt5.get(f"{MT5}/accounts", headers=bob.headers)
    assert len(mine.json()["data"]["accounts"]) == 1
    assert theirs.json()["data"]["accounts"] == []
    account_id = mine.json()["data"]["accounts"][0]["id"]
    foreign = await stack.mt5.get(f"{MT5}/accounts/{account_id}/status", headers=bob.headers)
    assert foreign.status_code == 404


async def test_sync_never_invents_deals(stack):
    admin = await stack.register(admin=True)
    link = await stack.mt5.post(f"{MT5}/accounts/link", headers=admin.headers)
    account_id = link.json()["data"]["account"]["id"]
    stack.terminal.account = None  # terminal closed after linking
    response = await stack.mt5.post(f"{MT5}/accounts/{account_id}/sync", headers=admin.headers)
    assert response.status_code == 409
    assert (await stack.summary(admin))["total_trades"] == 0

    # A different account in the terminal is refused too, never mixed into the linked one.
    stack.terminal.account = terminal_account(login=999, server="Other-Server")
    other = await stack.mt5.post(f"{MT5}/accounts/{account_id}/sync", headers=admin.headers)
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "TERMINAL_ACCOUNT_MISMATCH"
    assert (await stack.summary(admin))["total_trades"] == 0


async def test_synced_deals_reach_the_journal(stack):
    from mt5_fakes import closed_position_deals

    admin = await stack.register(admin=True)
    stack.terminal.deals = closed_position_deals()
    link = await stack.mt5.post(f"{MT5}/accounts/link", headers=admin.headers)
    account_id = link.json()["data"]["account"]["id"]
    await stack.mt5.post(f"{MT5}/accounts/{account_id}/sync", headers=admin.headers)
    trades = await stack.journal.get(f"{JOURNAL}/trades", headers=admin.headers)
    items = trades.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["source"] == "mt5"
    assert items[0]["symbol"] == "EURUSD"


async def test_rates_are_deterministic_and_never_random(stack):
    from mt5_fakes import candle

    admin = await stack.register(admin=True)
    stack.terminal.candles["XAUUSD"] = [candle("2026-03-02T15:00:00", "2300.5")]
    params = {"symbol": "XAUUSD", "timeframe": "H1", "count": 20}
    first = await stack.mt5.get(f"{MT5}/rates", params=params, headers=admin.headers)
    second = await stack.mt5.get(f"{MT5}/rates", params=params, headers=admin.headers)
    closes = [c["close"] for c in first.json()["data"]["candles"]]
    assert closes == [c["close"] for c in second.json()["data"]["candles"]] == [2300.5]
