import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from mt5_fakes import candle, closed_position_deals, deal, terminal_account

from mt5_service.application.use_cases.get_rates import GetRates
from mt5_service.application.use_cases.get_status import GetStatus
from mt5_service.application.use_cases.link_account import LinkAccount
from mt5_service.application.use_cases.list_accounts import ListAccounts
from mt5_service.application.use_cases.sync_account import SyncAccount
from mt5_service.application.use_cases.unlink_account import UnlinkAccount
from mt5_service.domain.account import LinkedAccount
from mt5_service.domain.deals import DealEntry, DealType
from mt5_service.domain.errors import (
    AccountAlreadyLinked,
    AccountNotFound,
    CountOutOfRange,
    InvalidTimeframe,
    JournalUnavailable,
    SymbolNotFound,
    TerminalAccountMismatch,
    TerminalNotAvailable,
)

D = Decimal


@pytest.fixture
def link(terminal, repo, clock, ids):
    return LinkAccount(terminal, repo, clock, ids)


@pytest.fixture
def sync(terminal, journal, repo, clock):
    return SyncAccount(terminal, journal, repo, clock)


@pytest.fixture
def status(terminal, repo, clock):
    return GetStatus(terminal, repo, clock)


async def test_link_uses_terminal_account_and_never_credentials(link, repo, clock):
    account = await link.execute("u1")

    assert account.account_ref == "123456@Demo-Server"
    assert (account.login, account.server, account.currency) == (123456, "Demo-Server", "USD")
    assert (account.name, account.trade_mode, account.company) == (
        "Jane Trader",
        "demo",
        "Demo Broker Ltd",
    )
    assert account.user_id == "u1"
    assert account.linked_at == clock.now()
    assert account.last_sync_at is None and account.last_sync_result is None
    assert await repo.get("u1", account.id) == account
    # The execute signature takes no credentials and no model carries one.
    fields = {f.name for f in dataclasses.fields(LinkedAccount)}
    fields |= {f.name for f in dataclasses.fields(type(terminal_account()))}
    assert not any("pass" in f or "secret" in f or "token" in f for f in fields)


async def test_link_when_terminal_unavailable_raises(link, terminal, repo):
    terminal.account = None
    with pytest.raises(TerminalNotAvailable):
        await link.execute("u1")
    assert repo.items == {}


async def test_link_other_users_account_raises_already_linked(link, repo):
    await link.execute("u1")
    with pytest.raises(AccountAlreadyLinked):
        await link.execute("u2")
    assert len(repo.items) == 1


async def test_relink_same_user_is_idempotent(link, repo):
    first = await link.execute("u1")
    second = await link.execute("u1")
    assert second == first
    assert len(repo.items) == 1


async def test_sync_mismatch_sends_nothing(link, sync, terminal, journal, repo):
    account = await link.execute("u1")
    terminal.account = terminal_account(login=999, server="Other")
    terminal.deals = closed_position_deals()

    with pytest.raises(TerminalAccountMismatch):
        await sync.execute("u1", account.id, "tok")

    assert journal.calls == []
    assert terminal.history_calls == 0
    assert (await repo.get("u1", account.id)).last_sync_at is None


async def test_sync_terminal_closed_sends_nothing(link, sync, terminal, journal):
    account = await link.execute("u1")
    terminal.account = None
    with pytest.raises(TerminalNotAvailable):
        await sync.execute("u1", account.id, "tok")
    assert journal.calls == []


async def test_sync_unknown_or_foreign_account_not_found(link, sync, journal):
    account = await link.execute("u1")
    with pytest.raises(AccountNotFound):
        await sync.execute("u2", account.id, "tok")
    with pytest.raises(AccountNotFound):
        await sync.execute("u1", "nope", "tok")
    assert journal.calls == []


async def test_sync_sends_trades_and_records_result(link, sync, terminal, journal, repo, clock):
    account = await link.execute("u1")
    terminal.deals = [
        *closed_position_deals(position_id=7),
        deal(20, 8, "2026-03-02T13:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.3"),
        deal(21, 0, "2026-03-01T09:00:00", DealType.BALANCE, DealEntry.IN, profit="1000"),
        deal(30, 11, "2026-03-02T10:00:00", DealType.BUY, DealEntry.IN, volume="1", price="1.1"),
        deal(31, 11, "2026-03-02T10:10:00", DealType.SELL, DealEntry.INOUT, volume="2", price="1.2"),
    ]  # fmt: skip

    result = await sync.execute("u1", account.id, "bearer-token")

    [(token, ref, trades, events)] = journal.calls
    assert (token, ref) == ("bearer-token", "123456@Demo-Server")
    [trade] = trades
    # Server tick 15:00:07 vs UTC 12:00 -> +3h: server 10:00 is 07:00Z.
    assert trade.open_time == datetime(2026, 3, 2, 7, 0, tzinfo=UTC)
    assert [(e.kind, e.amount) for e in events] == [("deposit", D("1000"))]
    assert (result.created, result.updated, result.balance_events) == (1, 0, 1)
    assert (result.open_positions, result.skipped_positions) == (1, 1)
    stored = await repo.get("u1", account.id)
    assert stored.last_sync_at == clock.now()
    assert stored.last_sync_result == result


async def test_sync_twice_sends_identical_payload(link, sync, terminal, journal):
    account = await link.execute("u1")
    terminal.deals = closed_position_deals()
    await sync.execute("u1", account.id, "t")
    await sync.execute("u1", account.id, "t")
    assert journal.calls[0][2] == journal.calls[1][2]


async def test_sync_journal_unavailable_does_not_record_sync(link, sync, terminal, journal, repo):
    account = await link.execute("u1")
    terminal.deals = closed_position_deals()
    journal.unavailable = True
    with pytest.raises(JournalUnavailable):
        await sync.execute("u1", account.id, "t")
    assert (await repo.get("u1", account.id)).last_sync_at is None


async def test_status_connected_reports_real_values(link, status, clock):
    account = await link.execute("u1")
    result = await status.execute("u1", account.id)
    assert result.connected is True
    assert (result.balance, result.equity) == (D("10000.00"), D("10050.25"))
    assert result.as_of == clock.now()
    assert result.last_sync_at is None


async def test_status_disconnected_has_no_balance(link, status, terminal):
    account = await link.execute("u1")
    terminal.account = None
    result = await status.execute("u1", account.id)
    assert result.connected is False
    assert result.balance is None and result.equity is None and result.as_of is None


async def test_status_other_account_in_terminal_is_disconnected(link, status, terminal):
    account = await link.execute("u1")
    terminal.account = terminal_account(login=1, server="X")
    result = await status.execute("u1", account.id)
    assert result.connected is False
    assert result.balance is None and result.equity is None and result.as_of is None


async def test_status_keeps_last_sync_at(link, sync, status, terminal, clock):
    account = await link.execute("u1")
    await sync.execute("u1", account.id, "t")
    assert (await status.execute("u1", account.id)).last_sync_at == clock.now()


async def test_users_cannot_see_each_others_accounts(link, status, terminal, repo):
    mine = await link.execute("u1")
    terminal.account = terminal_account(login=2, server="Demo-Server")
    theirs = await link.execute("u2")

    assert [a.id for a in await ListAccounts(repo).execute("u1")] == [mine.id]
    assert [a.id for a in await ListAccounts(repo).execute("u2")] == [theirs.id]
    with pytest.raises(AccountNotFound):
        await status.execute("u1", theirs.id)
    with pytest.raises(AccountNotFound):
        await UnlinkAccount(repo).execute("u1", theirs.id)
    assert len(repo.items) == 2


async def test_unlink_removes_account(link, repo):
    account = await link.execute("u1")
    await UnlinkAccount(repo).execute("u1", account.id)
    assert await ListAccounts(repo).execute("u1") == []


async def test_rates_convert_to_utc_with_server_offset(terminal, clock):
    terminal.candles["EURUSD"] = [
        candle("2026-03-02T15:00:00", "1.1"),
        candle("2026-03-02T16:00:00"),
    ]
    result = await GetRates(terminal, clock).execute("EURUSD", "H1", 2)
    assert [c.time for c in result] == [
        datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
        datetime(2026, 3, 2, 13, 0, tzinfo=UTC),
    ]
    assert result[0].close == D("1.1")


async def test_rates_unknown_symbol(terminal, clock):
    with pytest.raises(SymbolNotFound):
        await GetRates(terminal, clock).execute("NOPE", "H1", 10)


async def test_rates_terminal_unavailable(terminal, clock):
    terminal.account = None
    with pytest.raises(TerminalNotAvailable):
        await GetRates(terminal, clock).execute("EURUSD", "D1", 1)


@pytest.mark.parametrize("timeframe", ["M2", "h1", "", "W1"])
async def test_rates_invalid_timeframe(terminal, clock, timeframe):
    with pytest.raises(InvalidTimeframe):
        await GetRates(terminal, clock).execute("EURUSD", timeframe, 10)


@pytest.mark.parametrize("count", [0, -1, 1001])
async def test_rates_count_out_of_range(terminal, clock, count):
    with pytest.raises(CountOutOfRange):
        await GetRates(terminal, clock).execute("EURUSD", "M1", count)


@pytest.mark.parametrize("timeframe", ["M1", "M5", "M15", "M30", "H1", "H4", "D1"])
async def test_rates_accepts_all_timeframes(terminal, clock, timeframe):
    terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00")]
    assert len(await GetRates(terminal, clock).execute("EURUSD", timeframe, 1000)) == 1


async def test_rates_use_configured_offset_override(terminal, clock):
    terminal.tick_time = datetime(2026, 2, 27, 23, 59, 0)  # stale (weekend)
    terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00")]
    result = await GetRates(terminal, clock, server_utc_offset_minutes=120).execute(
        "EURUSD", "H1", 1
    )
    assert result[0].time == datetime(2026, 3, 2, 13, 0, tzinfo=UTC)


async def test_rates_with_stale_ticks_are_unavailable(terminal, clock):
    terminal.tick_time = datetime(2026, 2, 27, 23, 59, 0)
    terminal.candles["EURUSD"] = [candle("2026-03-02T15:00:00")]
    with pytest.raises(TerminalNotAvailable, match="stale"):
        await GetRates(terminal, clock).execute("EURUSD", "H1", 1)


async def test_sync_with_stale_ticks_writes_nothing(terminal, journal, repo, clock, ids):
    account = await LinkAccount(terminal, repo, clock, ids).execute("u1")
    terminal.deals = closed_position_deals()
    terminal.tick_time = datetime(2026, 2, 27, 23, 59, 0)
    with pytest.raises(TerminalNotAvailable, match="stale"):
        await SyncAccount(terminal, journal, repo, clock).execute("u1", account.id, "tok")
    assert journal.calls == []


async def test_sync_uses_configured_offset_override(terminal, journal, repo, clock, ids):
    account = await LinkAccount(terminal, repo, clock, ids).execute("u1")
    terminal.deals = closed_position_deals()
    terminal.tick_time = datetime(2026, 2, 27, 23, 59, 0)
    sync = SyncAccount(terminal, journal, repo, clock, server_utc_offset_minutes=120)
    await sync.execute("u1", account.id, "tok")
    assert journal.calls[0][2][0].open_time == datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
