from datetime import UTC, datetime
from decimal import Decimal

import pytest

from journal_service.application.ports.parsing import (
    ParsedBalanceEvent,
    ParsedReport,
    ReportAccount,
)
from journal_service.application.ports.repositories import TradeFilters
from journal_service.domain.errors import DuplicateImport, TradeNotFound
from journal_service.domain.report_import import SkippedRow
from journal_service.domain.trade import Outcome
from trading_shared.envelope import PageParams

pytestmark = pytest.mark.asyncio

ACCOUNT = ReportAccount(login="123", server="Broker-Live", currency="USD")


def report(trades, account=ACCOUNT, balance_events=(), skipped=()) -> ParsedReport:
    return ParsedReport(
        account=account,
        trades=list(trades),
        balance_events=list(balance_events),
        skipped_rows=list(skipped),
    )


def deposit(source_ref: str, amount: str = "1000") -> ParsedBalanceEvent:
    return ParsedBalanceEvent(
        kind="deposit",
        amount=Decimal(amount),
        time=datetime(2026, 1, 1, 7, 0, tzinfo=UTC),
        source_ref=source_ref,
        comment=None,
    )


async def test_import_creates_trades_and_balance_events(journal, parsed_trade):
    journal.parser.report = report(
        [parsed_trade("1"), parsed_trade("2")], balance_events=[deposit("dep-1")]
    )

    result = await journal.import_report().execute("u1", "r.csv", b"a")

    assert (result.trades_created, result.trades_updated, result.balance_events) == (2, 0, 1)
    assert result.created_at == journal.clock.now()
    assert len(await journal.trades.all_for("u1", None)) == 2
    assert len(await journal.balances.all_for("u1", None)) == 1
    assert journal.imports.items == [result]


async def test_same_file_twice_raises_duplicate_import_with_previous_id(journal, parsed_trade):
    journal.parser.report = report([parsed_trade("1")])
    first = await journal.import_report().execute("u1", "a.csv", b"same")

    with pytest.raises(DuplicateImport) as exc:
        await journal.import_report().execute("u1", "other-name.csv", b"same")

    assert exc.value.import_id == first.id
    assert exc.value.code == "DUPLICATE_IMPORT"
    assert exc.value.http_status == 409
    assert journal.parser.calls == 1


async def test_newer_report_updates_existing_positions_and_adds_new_ones(journal, parsed_trade):
    journal.parser.report = report([parsed_trade("1"), parsed_trade("2")])
    await journal.import_report().execute("u1", "a.csv", b"v1")
    journal.parser.report = report([parsed_trade("1"), parsed_trade("2"), parsed_trade("3")])

    second = await journal.import_report().execute("u1", "b.csv", b"v2")

    assert (second.trades_created, second.trades_updated) == (1, 2)
    assert len(await journal.trades.all_for("u1", None)) == 3


async def test_rows_without_position_id_deduplicate_by_row_hash(journal, parsed_trade):
    rows = [parsed_trade(None), parsed_trade(None, close_price=Decimal("1.2"))]
    journal.parser.report = report(rows)
    first = await journal.import_report().execute("u1", "a.csv", b"v1")
    assert first.trades_created == 2
    stored = await journal.trades.all_for("u1", None)
    assert all(t.row_hash and t.position_id is None for t in stored)

    # Same account (MT5 header) and same rows, different file bytes.
    journal.parser.report = report(rows)
    second = await journal.import_report().execute("u1", "b.csv", b"v2")

    assert (second.trades_created, second.trades_updated) == (0, 2)
    assert len(await journal.trades.all_for("u1", None)) == 2


async def test_flat_csv_import_uses_upload_account_ref(journal, parsed_trade):
    journal.parser.report = report([parsed_trade(None)], account=None)

    result = await journal.import_report().execute("u1", "flat.csv", b"x")

    assert result.account_ref == f"upload:{result.id}"
    (trade,) = await journal.trades.all_for("u1", None)
    assert trade.account_ref == f"upload:{result.id}"
    assert trade.import_id == result.id
    assert trade.source == "report"


async def test_mt5_report_uses_login_at_server_account_ref(journal, parsed_trade):
    journal.parser.report = report([parsed_trade("1")])

    result = await journal.import_report().execute("u1", "r.xlsx", b"x")

    assert result.account_ref == "123@Broker-Live"
    (trade,) = await journal.trades.all_for("u1", None)
    assert trade.account_ref == "123@Broker-Live"


async def test_skipped_rows_are_recorded(journal, parsed_trade):
    skipped = [SkippedRow(row=7, reason="invalid volume")]
    journal.parser.report = report([parsed_trade("1")], skipped=skipped)

    result = await journal.import_report().execute("u1", "r.csv", b"x")

    assert result.skipped_rows == skipped
    assert result.trades_created == 1


async def test_users_are_isolated(journal, parsed_trade):
    journal.parser.report = report([parsed_trade("1")])
    await journal.import_report().execute("u1", "r.csv", b"x")
    (trade,) = await journal.trades.all_for("u1", None)

    trades, total = await journal.list_trades().execute("u2", TradeFilters(), PageParams())
    assert (trades, total) == ([], 0)
    assert await journal.list_accounts().execute("u2") == []
    assert await journal.list_imports().execute("u2", PageParams()) == ([], 0)
    with pytest.raises(TradeNotFound) as exc:
        await journal.get_trade().execute("u2", trade.id)
    assert exc.value.code == "NOT_FOUND"
    assert exc.value.http_status == 404
    dataset = await journal.dataset().execute("u2", None)
    assert dataset.trades == [] and dataset.balance_events == []
    # The same file is not a duplicate for another user.
    other = await journal.import_report().execute("u2", "r.csv", b"x")
    assert other.user_id == "u2"
    assert (await journal.get_trade().execute("u1", trade.id)).id == trade.id


async def test_net_includes_commission_and_swap(make_trade):
    trade = make_trade(profit=Decimal("100"), commission=Decimal("-7"), swap=Decimal("-3"))
    assert trade.net == Decimal("90")
    assert trade.outcome is Outcome.WIN
    assert trade.duration_minutes == 90


async def test_outcome_breakeven_when_net_is_zero(make_trade):
    trade = make_trade(profit=Decimal("10"), commission=Decimal("-7"), swap=Decimal("-3"))
    assert trade.net == Decimal("0")
    assert trade.outcome is Outcome.BREAKEVEN
    assert make_trade(profit=Decimal("-1")).outcome is Outcome.LOSS


async def test_trade_rejects_naive_datetimes(make_trade):
    with pytest.raises(ValueError):
        make_trade(open_time=datetime(2026, 1, 1, 8, 0))


async def test_ingest_mt5_history_is_idempotent(journal, parsed_trade):
    trades = [parsed_trade("11"), parsed_trade("12")]

    first = await journal.ingest().execute("u1", "999@Demo", trades, [deposit("deal-9", "500")])
    second = await journal.ingest().execute("u1", "999@Demo", trades, [deposit("deal-9", "500")])

    assert (first.created, first.updated, first.balance_events) == (2, 0, 1)
    assert (second.created, second.updated, second.balance_events) == (0, 2, 1)
    stored = await journal.trades.all_for("u1", "999@Demo")
    assert len(stored) == 2 and all(t.source == "mt5" and t.import_id is None for t in stored)
    assert len(await journal.balances.all_for("u1", "999@Demo")) == 1
