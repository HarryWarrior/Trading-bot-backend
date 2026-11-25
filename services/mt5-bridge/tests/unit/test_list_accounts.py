from datetime import timedelta
from decimal import Decimal

from mt5_bridge_service.application.use_cases.list_accounts import ListAccounts
from mt5_bridge_service.application.use_cases.record_heartbeat import RecordHeartbeat
from mt5_bridge_service.domain.account import AccountStatus, Heartbeat


def _hb(login: int) -> Heartbeat:
    return Heartbeat(login=login, server="Srv", balance=Decimal(1), equity=Decimal(1))


async def test_list_accounts_only_returns_own_user(accounts, clock):
    record = RecordHeartbeat(accounts, clock)
    await record.execute("u1", _hb(1))
    await record.execute("u2", _hb(2))

    listed = await ListAccounts(accounts, clock).execute("u1")

    assert [item.account.account_ref for item in listed] == ["1@Srv"]
    assert all(item.account.user_id == "u1" for item in listed)
    assert await ListAccounts(accounts, clock).execute("nobody") == []


async def test_list_accounts_reports_status_at_current_time(accounts, clock):
    record = RecordHeartbeat(accounts, clock)
    await record.execute("u1", _hb(1))
    clock.advance(timedelta(minutes=10))
    await record.execute("u1", _hb(2))

    listed = await ListAccounts(accounts, clock).execute("u1")

    assert {i.account.account_ref: i.status for i in listed} == {
        "1@Srv": AccountStatus.DISCONNECTED,
        "2@Srv": AccountStatus.CONNECTED,
    }
