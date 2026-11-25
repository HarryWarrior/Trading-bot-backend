"""End-to-end scenarios across auth, journal, analytics and mt5 (harness in harness.py)."""

from __future__ import annotations

from mt5_fakes import candle, closed_position_deals

from tests.acceptance_services.harness import (
    ANALYTICS,
    AUTH,
    JOURNAL,
    MT5,
    PASSWORD,
    SAMPLE,
)


async def test_sign_up_to_kpis_full_flow(stack):
    email = await stack.sign_up()
    # Unverified accounts cannot sign in; the code only ever travels by email.
    early = await stack.auth.post(f"{AUTH}/sign-in", json={"email": email, "password": PASSWORD})
    assert early.status_code == 403
    code = stack.sender.last_code(email)
    verified = await stack.auth.post(f"{AUTH}/verify-email", json={"email": email, "code": code})
    assert verified.status_code == 200
    session = await stack.sign_in(email)

    uploaded = await stack.upload(session, "sample_trades.csv", SAMPLE.read_bytes())
    assert uploaded.status_code == 201
    summary = await stack.summary(session)
    assert summary["net_profit"] == 1450.00
    assert summary["win_rate"] == 70.00
    assert summary["total_trades"] == 10

    me = await stack.auth.get(f"{AUTH}/me", headers=session.headers)
    assert me.json()["data"]["user"]["email"] == email


async def test_second_user_is_isolated(stack):
    alice = await stack.register()
    bob = await stack.register()
    assert (await stack.upload(alice, "sample_trades.csv", SAMPLE.read_bytes())).status_code == 201

    assert (await stack.summary(alice))["total_trades"] == 10
    assert (await stack.summary(bob))["total_trades"] == 0
    trades = await stack.journal.get(f"{JOURNAL}/trades", headers=bob.headers)
    assert trades.json()["data"]["items"] == []
    imports = await stack.journal.get(f"{JOURNAL}/imports", headers=bob.headers)
    assert imports.json()["data"]["items"] == []


async def test_duplicate_upload_is_409(stack):
    session = await stack.register()
    content = SAMPLE.read_bytes()
    assert (await stack.upload(session, "sample_trades.csv", content)).status_code == 201
    again = await stack.upload(session, "sample_trades.csv", content)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "DUPLICATE_IMPORT"
    assert (await stack.summary(session))["total_trades"] == 10


async def test_refresh_rotates_the_token(stack):
    session = await stack.register()
    first = await stack.auth.post(f"{AUTH}/refresh", json={"refresh_token": session.refresh_token})
    assert first.status_code == 200
    rotated = first.json()["data"]["refresh_token"]
    assert rotated != session.refresh_token
    # The old refresh token is single use.
    replay = await stack.auth.post(f"{AUTH}/refresh", json={"refresh_token": session.refresh_token})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "INVALID_TOKEN"
    again = await stack.auth.post(f"{AUTH}/refresh", json={"refresh_token": rotated})
    assert again.status_code == 200


async def test_non_admin_cannot_touch_mt5_but_can_read(stack):
    user = await stack.register()
    assert user.role == "user"
    for call in (
        stack.mt5.post(f"{MT5}/accounts/link", headers=user.headers),
        stack.mt5.post(f"{MT5}/accounts/x/sync", headers=user.headers),
        stack.mt5.delete(f"{MT5}/accounts/x", headers=user.headers),
    ):
        response = await call
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
    listed = await stack.mt5.get(f"{MT5}/accounts", headers=user.headers)
    assert listed.status_code == 200
    assert listed.json()["data"]["accounts"] == []


async def test_terminal_unavailable_is_409_everywhere(stack):
    admin = await stack.register(admin=True)
    assert admin.role == "admin"
    stack.terminal.account = None
    link = await stack.mt5.post(f"{MT5}/accounts/link", headers=admin.headers)
    assert link.status_code == 409
    assert link.json()["error"]["code"] == "TERMINAL_NOT_AVAILABLE"
    rates = await stack.mt5.get(
        f"{MT5}/rates", params={"symbol": "EURUSD", "timeframe": "H1"}, headers=admin.headers
    )
    assert rates.status_code == 409


async def test_admin_links_syncs_and_sees_real_trades(stack):
    admin = await stack.register(admin=True)
    stack.terminal.deals = closed_position_deals()
    link = await stack.mt5.post(f"{MT5}/accounts/link", headers=admin.headers)
    assert link.status_code == 201
    account_id = link.json()["data"]["account"]["id"]

    sync = await stack.mt5.post(f"{MT5}/accounts/{account_id}/sync", headers=admin.headers)
    assert sync.status_code == 200
    assert sync.json()["data"]["result"]["created"] == 1
    # Journal and analytics now show the synced trade for this user only.
    summary = await stack.summary(admin)
    assert summary["total_trades"] == 1
    assert summary["net_profit"] == 46.0
    other = await stack.register()
    assert (await stack.summary(other))["total_trades"] == 0
    assert ANALYTICS  # path constant used by the harness helpers
    # Running it twice creates nothing new.
    again = await stack.mt5.post(f"{MT5}/accounts/{account_id}/sync", headers=admin.headers)
    assert again.json()["data"]["result"]["created"] == 0
    assert (await stack.summary(admin))["total_trades"] == 1


async def test_rates_come_from_the_terminal_only(stack):
    admin = await stack.register(admin=True)
    stack.terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00", "1.10555")]
    params = {"symbol": "EURUSD", "timeframe": "H1", "count": 5}
    first = await stack.mt5.get(f"{MT5}/rates", params=params, headers=admin.headers)
    second = await stack.mt5.get(f"{MT5}/rates", params=params, headers=admin.headers)
    assert first.status_code == 200
    assert first.json()["data"]["candles"] == second.json()["data"]["candles"]
    unknown = await stack.mt5.get(
        f"{MT5}/rates", params={**params, "symbol": "NOPE"}, headers=admin.headers
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "SYMBOL_NOT_FOUND"
