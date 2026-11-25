from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from mt5_bridge_service.application.use_cases.ingest_deals import IngestDeals
from mt5_bridge_service.application.use_cases.record_heartbeat import RecordHeartbeat
from mt5_bridge_service.domain.account import Heartbeat
from mt5_bridge_service.domain.deal import MAX_DEALS_PER_REQUEST, RawDeal
from mt5_bridge_service.domain.errors import InvalidDealBatch, JournalUnavailable

T0 = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
REF = "123456@Demo-Server"


def deal(ticket: int = 1, time: datetime = T0) -> RawDeal:
    return RawDeal(
        ticket=ticket,
        position_id=7,
        time=time,
        type=0,
        entry=0,
        symbol="EURUSD",
        volume=Decimal("1.0"),
        price=Decimal("1.1"),
        commission=Decimal("-1"),
        swap=Decimal("0"),
        profit=Decimal("0"),
        sl=None,
        tp=None,
        comment=None,
    )


async def heartbeat(accounts, clock, user_id: str = "u1") -> None:
    hb = Heartbeat(login=123456, server="Demo-Server", balance=Decimal(1), equity=Decimal(1))
    await RecordHeartbeat(accounts, clock).execute(user_id, hb)


async def test_forwards_with_owner_and_account_ref(journal, accounts):
    result = await IngestDeals(journal, accounts).execute(
        "u1", 123456, " Demo-Server ", [deal(1), deal(2)]
    )
    assert result.received == 2
    assert [(u, ref, [d.ticket for d in ds]) for u, ref, ds in journal.calls] == [
        ("u1", REF, [1, 2])
    ]


async def test_updates_last_deal_at_to_newest_deal_and_never_lowers_it(journal, accounts, clock):
    await heartbeat(accounts, clock)
    use_case = IngestDeals(journal, accounts)
    newest = T0 + timedelta(hours=2)
    await use_case.execute("u1", 123456, "Demo-Server", [deal(1, T0), deal(2, newest)])
    await use_case.execute("u1", 123456, "Demo-Server", [deal(3, T0 - timedelta(days=30))])
    [account] = await accounts.list_for_user("u1")
    assert account.last_deal_at == newest


async def test_empty_batch_is_not_forwarded(journal, accounts):
    result = await IngestDeals(journal, accounts).execute("u1", 123456, "Demo-Server", [])
    assert (result.received, result.new, result.trades_upserted) == (0, 0, 0)
    assert journal.calls == []


async def test_more_than_the_cap_is_rejected_and_nothing_forwarded(journal, accounts):
    deals = [deal(i) for i in range(MAX_DEALS_PER_REQUEST + 1)]
    with pytest.raises(InvalidDealBatch):
        await IngestDeals(journal, accounts).execute("u1", 123456, "Demo-Server", deals)
    assert journal.calls == []


@pytest.mark.parametrize(("login", "server"), [(0, "Demo"), (-1, "Demo"), (1, "  ")])
async def test_invalid_account_identity_is_rejected(journal, accounts, login, server):
    with pytest.raises(InvalidDealBatch):
        await IngestDeals(journal, accounts).execute("u1", login, server, [deal()])
    assert journal.calls == []


async def test_journal_down_propagates_and_last_deal_at_stays(journal, accounts, clock):
    await heartbeat(accounts, clock)
    journal.error = JournalUnavailable()
    with pytest.raises(JournalUnavailable):
        await IngestDeals(journal, accounts).execute("u1", 123456, "Demo-Server", [deal()])
    [account] = await accounts.list_for_user("u1")
    assert account.last_deal_at is None


def test_cap_is_200():
    assert MAX_DEALS_PER_REQUEST == 200
