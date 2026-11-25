from datetime import UTC, datetime
from decimal import Decimal

from journal_service.domain.deals import DealEntry, DealType, RawDeal

ACCOUNT = "123@Demo-Server"
D = Decimal


def deal(
    ticket: int,
    position_id: int,
    hour: int,
    type: int,
    entry: int,
    *,
    volume: str = "1",
    price: str = "1.1",
    profit: str = "0",
) -> RawDeal:
    return RawDeal(
        ticket=ticket,
        position_id=position_id,
        time=datetime(2026, 3, 2, hour, 0, tzinfo=UTC),
        type=type,
        entry=entry,
        symbol="EURUSD",
        volume=D(volume),
        price=D(price),
        commission=D("-1"),
        swap=D("0"),
        profit=D(profit),
        sl=None,
        tp=None,
        comment=None,
    )


ENTRY = deal(1, 7, 8, DealType.BUY, DealEntry.IN)
EXIT = deal(2, 7, 9, DealType.SELL, DealEntry.OUT, price="1.2", profit="100")
DEPOSIT = deal(3, 0, 7, DealType.BALANCE, DealEntry.IN, volume="0", price="0", profit="500")


async def test_same_deal_twice_creates_one_raw_deal_and_one_trade(journal):
    use_case = journal.ingest_deals()

    first = await use_case.execute("u1", ACCOUNT, [ENTRY, EXIT, DEPOSIT])
    second = await use_case.execute("u1", ACCOUNT, [ENTRY, EXIT, DEPOSIT])

    assert (first.received, first.new, first.trades_upserted) == (3, 3, 1)
    assert (second.received, second.new, second.trades_upserted) == (3, 0, 1)
    assert len(journal.deals.rows) == 3
    [trade] = await journal.trades.all_for("u1", ACCOUNT)
    assert trade.position_id == "7"
    assert trade.source == "mt5"
    assert trade.profit == D("100")
    assert trade.commission == D("-2")
    assert trade.user_id == "u1"
    [event] = await journal.balances.all_for("u1", ACCOUNT)
    assert (event.kind, event.amount, event.source_ref) == ("deposit", D("500"), "3")


async def test_late_exit_completes_trade_from_stored_entry(journal):
    use_case = journal.ingest_deals()

    opened = await use_case.execute("u1", ACCOUNT, [ENTRY])
    assert opened.trades_upserted == 0
    assert await journal.trades.all_for("u1", ACCOUNT) == []

    closed = await use_case.execute("u1", ACCOUNT, [EXIT])

    assert (closed.new, closed.trades_upserted) == (1, 1)
    [trade] = await journal.trades.all_for("u1", ACCOUNT)
    assert trade.open_time == ENTRY.time
    assert trade.close_time == EXIT.time
    assert trade.open_price == D("1.1")
    assert trade.close_price == D("1.2")


async def test_stored_deals_of_other_users_and_accounts_are_not_paired(journal):
    use_case = journal.ingest_deals()
    await use_case.execute("u2", ACCOUNT, [ENTRY])
    await use_case.execute("u1", "999@Other", [ENTRY])

    result = await use_case.execute("u1", ACCOUNT, [EXIT])

    assert result.trades_upserted == 0
    assert result.skipped == [("7", "no entry deal in the history")]
    assert await journal.trades.all_for("u1", None) == []


async def test_inout_position_is_reported_as_skipped(journal):
    reversal = deal(4, 8, 10, DealType.SELL, DealEntry.INOUT, volume="2")
    result = await journal.ingest_deals().execute(
        "u1", ACCOUNT, [deal(5, 8, 9, DealType.BUY, DealEntry.IN), reversal]
    )
    assert result.trades_upserted == 0
    [(position_id, reason)] = result.skipped
    assert position_id == "8"
    assert "INOUT" in reason


async def test_empty_batch_is_a_no_op(journal):
    result = await journal.ingest_deals().execute("u1", ACCOUNT, [])
    assert (result.received, result.new, result.trades_upserted) == (0, 0, 0)
