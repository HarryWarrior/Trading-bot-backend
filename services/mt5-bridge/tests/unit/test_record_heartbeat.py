from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from mt5_bridge_service.application.use_cases.record_heartbeat import RecordHeartbeat
from mt5_bridge_service.domain.account import Heartbeat


def _hb(balance: str = "1000", login: int = 123, server: str = "Broker-Demo") -> Heartbeat:
    return Heartbeat(login=login, server=server, balance=Decimal(balance), equity=Decimal(balance))


async def test_heartbeat_upserts_account_by_account_ref(accounts, clock):
    record = RecordHeartbeat(accounts, clock)
    first = await record.execute("u1", _hb("1000"))
    key = ("u1", "123@Broker-Demo")
    accounts.rows[key] = replace(accounts.rows[key], last_deal_at=clock.now())
    clock.advance(timedelta(seconds=60))

    second = await record.execute("u1", _hb("1050"))

    assert first.account_ref == second.account_ref == "123@Broker-Demo"
    assert list(accounts.rows) == [key]
    assert second.balance == Decimal("1050")
    assert second.last_heartbeat == clock.now()
    assert second.last_deal_at is not None  # a heartbeat never clears deal activity


async def test_same_account_of_two_users_stays_separate(accounts, clock):
    record = RecordHeartbeat(accounts, clock)
    await record.execute("u1", _hb())
    await record.execute("u2", _hb())
    await record.execute("u1", _hb(login=456))

    assert set(accounts.rows) == {
        ("u1", "123@Broker-Demo"),
        ("u2", "123@Broker-Demo"),
        ("u1", "456@Broker-Demo"),
    }
