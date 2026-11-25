"""EA bridge flow across auth, mt5-bridge and journal: token, push deals, trades, isolation."""

from __future__ import annotations

from tests.acceptance_services.harness import BRIDGE, JOURNAL

ACCOUNT = {"account_login": 5001234, "server": "Broker-Demo"}


def deal(ticket: int, time: str, side: int, entry: int, **extra) -> dict:
    return {
        "ticket": ticket,
        "position_id": 900,
        "time": time,
        "type": side,
        "entry": entry,
        "symbol": "EURUSD",
        "volume": "1.0",
        "price": "1.1000",
        **extra,
    }


ENTRY = deal(1, "2026-03-02T10:00:00Z", 0, 0, commission="-2")
EXIT = deal(2, "2026-03-02T11:00:00Z", 1, 1, price="1.1050", commission="-2", profit="50")


async def issue_token(stack, session, name: str = "ea") -> tuple[str, str]:
    response = await stack.bridge.post(
        f"{BRIDGE}/tokens", json={"name": name}, headers=session.headers
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    return data["token"]["id"], data["plaintext_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def push(stack, token: str, deals: list[dict]):
    return await stack.bridge.post(
        f"{BRIDGE}/ingest/deals", json={**ACCOUNT, "deals": deals}, headers=bearer(token)
    )


async def trades(stack, session) -> list[dict]:
    response = await stack.journal.get(f"{JOURNAL}/trades", headers=session.headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


async def test_ea_pushes_deals_and_journal_shows_one_trade(stack):
    user = await stack.register()
    _, token = await issue_token(stack, user)

    first = await push(stack, token, [ENTRY, EXIT])
    assert first.status_code == 200, first.text
    assert first.json()["data"]["new"] == 2

    items = await trades(stack, user)
    assert len(items) == 1
    assert items[0]["side"] == "buy"
    assert items[0]["profit"] == 50.0
    assert items[0]["symbol"] == "EURUSD"

    # Resending the same deals (EA retry) creates nothing new.
    again = await push(stack, token, [ENTRY, EXIT])
    assert again.status_code == 200
    assert again.json()["data"]["new"] == 0
    assert len(await trades(stack, user)) == 1


async def test_revoked_token_is_rejected(stack):
    user = await stack.register()
    token_id, token = await issue_token(stack, user)
    assert (await push(stack, token, [ENTRY])).status_code == 200

    revoked = await stack.bridge.delete(f"{BRIDGE}/tokens/{token_id}", headers=user.headers)
    assert revoked.status_code == 200
    rejected = await push(stack, token, [EXIT])
    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_heartbeat_makes_the_account_connected(stack):
    user = await stack.register()
    _, token = await issue_token(stack, user)
    beat = await stack.bridge.post(
        f"{BRIDGE}/ingest/heartbeat",
        json={**ACCOUNT, "balance": "10000.50", "equity": "10010.25", "terminal_build": 4500},
        headers=bearer(token),
    )
    assert beat.status_code == 200, beat.text

    listed = await stack.bridge.get(f"{BRIDGE}/accounts", headers=user.headers)
    accounts = listed.json()["data"]["items"]
    assert [a["account_ref"] for a in accounts] == ["5001234@Broker-Demo"]
    assert accounts[0]["status"] == "connected"
    assert accounts[0]["balance"] == 10000.5


async def test_second_user_sees_nothing_of_the_first(stack):
    alice = await stack.register()
    bob = await stack.register()
    _, token = await issue_token(stack, alice)
    assert (await push(stack, token, [ENTRY, EXIT])).status_code == 200
    beat = await stack.bridge.post(
        f"{BRIDGE}/ingest/heartbeat",
        json={**ACCOUNT, "balance": "1", "equity": "1"},
        headers=bearer(token),
    )
    assert beat.status_code == 200, beat.text

    assert len(await trades(stack, alice)) == 1
    own_accounts = await stack.bridge.get(f"{BRIDGE}/accounts", headers=alice.headers)
    assert len(own_accounts.json()["data"]["items"]) == 1
    own_tokens = await stack.bridge.get(f"{BRIDGE}/tokens", headers=alice.headers)
    assert len(own_tokens.json()["data"]["items"]) == 1
    assert await trades(stack, bob) == []
    accounts = await stack.bridge.get(f"{BRIDGE}/accounts", headers=bob.headers)
    assert accounts.json()["data"]["items"] == []
    tokens = await stack.bridge.get(f"{BRIDGE}/tokens", headers=bob.headers)
    assert tokens.json()["data"]["items"] == []
