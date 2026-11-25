import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pymongo.errors
import pytest
import pytest_asyncio

from journal_service.adapters.outbound.mongo_repositories import (
    MongoBalanceRepository,
    MongoDealRepository,
    MongoImportRepository,
    MongoTradeRepository,
)
from journal_service.adapters.outbound.system_clock import SystemClock
from journal_service.adapters.outbound.uuid_ids import UuidIdGenerator
from journal_service.application.ports.repositories import TradeFilters
from journal_service.domain.balance import BalanceEvent
from journal_service.domain.deals import RawDeal
from journal_service.domain.errors import DuplicateImport
from journal_service.domain.report_import import ReportImport, SkippedRow
from journal_service.domain.trade import Outcome
from trading_shared.mongo import create_mongo_client

MONGO_URL = "mongodb://localhost:27017"
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def db():
    client = create_mongo_client(MONGO_URL)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    database = client[f"test_journal_{uuid.uuid4().hex}"]
    try:
        yield database
    finally:
        await client.drop_database(database.name)
        client.close()


@pytest_asyncio.fixture
async def trades(db):
    repo = MongoTradeRepository(db)
    await repo.create_indexes()
    return repo


async def _list(repo, user="u1", filters=None, page=1, size=50, sort_by=None, sort_dir="desc"):
    return await repo.list(user, filters or TradeFilters(), page, size, sort_by, sort_dir)


def test_system_clock_and_ids():
    assert SystemClock().now().tzinfo is not None
    ids = UuidIdGenerator()
    assert ids.new_id() != ids.new_id()


async def test_upsert_twice_keeps_id_and_reports_counts(trades, make_trade):
    t = make_trade(id="a")
    assert await trades.upsert_many("u1", [t]) == (1, 0)
    changed = replace(t, id="zzz", profit=Decimal("99"))
    assert await trades.upsert_many("u1", [changed]) == (0, 1)
    got, total = await _list(trades)
    assert total == 1
    assert got[0].id == "a"
    assert got[0].profit == Decimal("99")
    # net stays consistent after update
    wins, _ = await _list(trades, filters=TradeFilters(profit_min=Decimal("99")))
    assert len(wins) == 1


async def test_upsert_empty_and_mixed_counts(trades, make_trade):
    assert await trades.upsert_many("u1", []) == (0, 0)
    await trades.upsert_many("u1", [make_trade(id="a", position_id="1")])
    batch = [make_trade(id="b", position_id="1"), make_trade(id="c", position_id="2")]
    assert await trades.upsert_many("u1", batch) == (1, 1)


async def test_row_hash_natural_key_and_no_collision_between_keys(trades, make_trade):
    h1 = make_trade(id="a", position_id=None, row_hash="h1")
    h2 = make_trade(id="b", position_id=None, row_hash="h2")
    assert await trades.upsert_many("u1", [h1, h2]) == (2, 0)
    assert await trades.upsert_many("u1", [h1]) == (0, 1)
    assert (await _list(trades))[1] == 2


async def test_ownership_mismatch_rejected(trades, make_trade):
    with pytest.raises(ValueError):
        await trades.upsert_many("u2", [make_trade(user_id="u1")])


async def test_partial_unique_indexes_reject_duplicates(db, trades):
    col = db["trades"]
    doc = {"user_id": "u1", "account_ref": "a", "position_id": "1"}
    await col.insert_one({"_id": "1", **doc})
    with pytest.raises(pymongo.errors.DuplicateKeyError):
        await col.insert_one({"_id": "2", **doc})
    hdoc = {"user_id": "u1", "account_ref": "a", "row_hash": "x"}
    await col.insert_one({"_id": "3", **hdoc})
    with pytest.raises(pymongo.errors.DuplicateKeyError):
        await col.insert_one({"_id": "4", **hdoc})
    # documents lacking both keys do not collide
    await col.insert_one({"_id": "5", "user_id": "u1", "account_ref": "a"})
    await col.insert_one({"_id": "6", "user_id": "u1", "account_ref": "a"})


async def test_same_position_other_user_or_account_allowed(trades, make_trade):
    await trades.upsert_many("u1", [make_trade(id="a")])
    assert await trades.upsert_many("u2", [make_trade(id="b", user_id="u2")]) == (1, 0)
    assert await trades.upsert_many("u1", [make_trade(id="c", account_ref="other")]) == (1, 0)


async def test_list_filters(trades, make_trade):
    d = timedelta
    rows = [
        make_trade(
            id="1",
            position_id="1",
            symbol="EURUSD",
            profit=Decimal("50"),
            close_time=T0,
            comment="Breakout setup",
        ),
        make_trade(
            id="2",
            position_id="2",
            symbol="XAUUSD",
            profit=Decimal("-30"),
            close_time=T0 + d(days=1),
            account_ref="acc2",
        ),
        make_trade(
            id="3",
            position_id="3",
            symbol="EURUSD",
            profit=Decimal("10"),
            commission=Decimal("-10"),
            close_time=T0 + d(days=2),
        ),
        make_trade(
            id="4",
            position_id="4",
            symbol="GBPUSD",
            profit=Decimal("5"),
            close_time=T0 + d(days=3),
            comment="a.b (test)",
        ),
    ]
    await trades.upsert_many("u1", rows)

    async def ids(**kw):
        got, total = await _list(
            trades, filters=TradeFilters(**kw), sort_by="close_time", sort_dir="asc"
        )
        assert total == len(got)
        return [t.id for t in got]

    assert await ids(symbol="eurusd") == ["1", "3"]
    assert await ids(outcome=Outcome.WIN) == ["1", "4"]
    assert await ids(outcome=Outcome.LOSS) == ["2"]
    assert await ids(outcome=Outcome.BREAKEVEN) == ["3"]
    # date_from inclusive, date_to exclusive
    assert await ids(date_from=T0 + d(days=1), date_to=T0 + d(days=3)) == ["2", "3"]
    assert await ids(profit_min=Decimal("5"), profit_max=Decimal("50")) == ["1", "4"]
    assert await ids(account_ref="acc2") == ["2"]
    assert await ids(q="BREAKOUT") == ["1"]
    assert await ids(q="gbp") == ["4"]
    assert await ids(q="a.b (") == ["4"]
    assert await ids(q=".*") == []
    assert await ids(symbol="EURUSD", outcome=Outcome.WIN, q="eur") == ["1"]


async def test_list_sorts_and_pagination(trades, make_trade):
    specs = [("BBB", "5", 3, 10), ("AAA", "-5", 1, 30), ("CCC", "9", 2, 20), ("AAA", "0", 4, 40)]
    rows = [
        make_trade(
            id=str(i),
            position_id=str(i),
            symbol=s,
            profit=Decimal(p),
            open_time=T0 + timedelta(hours=o),
            close_time=T0 + timedelta(hours=c),
        )
        for i, (s, p, o, c) in enumerate(specs)
    ]
    await trades.upsert_many("u1", rows)

    async def order(sort_by, sort_dir):
        got, _ = await _list(trades, sort_by=sort_by, sort_dir=sort_dir)
        return [t.id for t in got]

    assert await order("close_time", "asc") == ["0", "2", "1", "3"]
    assert await order("close_time", "desc") == ["3", "1", "2", "0"]
    assert await order("open_time", "asc") == ["1", "2", "0", "3"]
    assert await order("profit", "desc") == ["2", "0", "3", "1"]
    assert await order("symbol", "asc") == ["1", "3", "0", "2"]  # tie AAA broken by _id
    assert await order(None, "desc") == ["3", "1", "2", "0"]

    page2, total = await _list(trades, page=2, size=3, sort_by="close_time", sort_dir="asc")
    assert total == 4
    assert [t.id for t in page2] == ["3"]


async def test_get_is_scoped_to_user(trades, make_trade):
    await trades.upsert_many("u1", [make_trade(id="a")])
    assert (await trades.get("u1", "a")).id == "a"
    assert await trades.get("u2", "a") is None
    assert await trades.get("u1", "missing") is None
    assert await _list(trades, user="u2") == ([], 0)


async def test_all_for_and_accounts(trades, make_trade):
    await trades.upsert_many(
        "u1",
        [
            make_trade(id="1", position_id="1", close_time=T0),
            make_trade(id="2", position_id="2", close_time=T0 + timedelta(days=2)),
            make_trade(
                id="3", position_id="3", account_ref="acc2", close_time=T0 + timedelta(days=1)
            ),
        ],
    )
    await trades.upsert_many("u2", [make_trade(id="9", user_id="u2", account_ref="zzz")])
    assert len(await trades.all_for("u1", None)) == 3
    assert [t.id for t in await trades.all_for("u1", "acc2")] == ["3"]
    by_ref = {a.account_ref: a for a in await trades.accounts("u1")}
    assert set(by_ref) == {"123@Broker-Live", "acc2"}
    main = by_ref["123@Broker-Live"]
    assert main.trades == 2
    assert main.first_trade_at == T0
    assert main.last_trade_at == T0 + timedelta(days=2)
    assert main.first_trade_at.tzinfo is not None
    assert await trades.accounts("nobody") == []


async def test_decimal_roundtrip_exact(trades, make_trade):
    t = make_trade(
        id="a",
        profit=Decimal("0.1") + Decimal("0.2"),
        volume=Decimal("0.10"),
        stop_loss=Decimal("1.09950"),
        take_profit=None,
        commission=Decimal("-0.07"),
    )
    await trades.upsert_many("u1", [t])
    got = await trades.get("u1", "a")
    assert got == t
    assert got.profit == Decimal("0.3")
    assert isinstance(got.profit, Decimal)
    assert got.open_time.tzinfo is not None


def _event(**kw) -> BalanceEvent:
    base = {
        "id": "e1",
        "user_id": "u1",
        "account_ref": "a",
        "kind": "deposit",
        "amount": Decimal("100.10"),
        "time": T0,
        "source_ref": "s1",
        "comment": None,
    }
    base.update(kw)
    return BalanceEvent(**base)


async def test_balance_upsert_and_ownership(db):
    repo = MongoBalanceRepository(db)
    await repo.create_indexes()
    assert await repo.upsert_many("u1", [_event()]) == 1
    again = _event(id="other", amount=Decimal("-5"), kind="withdrawal")
    assert await repo.upsert_many("u1", [again]) == 0  # updated, not new
    got = await repo.all_for("u1", None)
    assert len(got) == 1
    assert got[0].id == "e1"
    assert got[0].amount == Decimal("-5")
    assert await repo.all_for("u1", "nope") == []
    assert await repo.all_for("u2", None) == []
    assert await repo.upsert_many("u1", []) == 0
    with pytest.raises(ValueError):
        await repo.upsert_many("u2", [_event()])


async def test_adjustment_event_round_trips(db):
    repo = MongoBalanceRepository(db)
    await repo.create_indexes()
    await repo.upsert_many("u1", [_event(kind="adjustment", amount=Decimal("-3.50"))])
    (got,) = await repo.all_for("u1", None)
    assert (got.kind, got.amount) == ("adjustment", Decimal("-3.50"))


def _import(**kw) -> ReportImport:
    base = {
        "id": "i1",
        "user_id": "u1",
        "filename": "r.csv",
        "sha256": "abc",
        "account_ref": "a",
        "trades_created": 2,
        "trades_updated": 1,
        "balance_events": 0,
        "created_at": T0,
        "skipped_rows": [SkippedRow(row=3, reason="bad")],
    }
    base.update(kw)
    return ReportImport(**base)


async def test_imports_roundtrip_list_and_isolation(db):
    repo = MongoImportRepository(db)
    await repo.create_indexes()
    await repo.add(_import())
    await repo.add(_import(id="i2", sha256="def", created_at=T0 + timedelta(hours=1)))
    assert await repo.find_by_sha("u1", "abc") == _import()
    assert await repo.find_by_sha("u2", "abc") is None
    items, total = await repo.list("u1", 1, 10)
    assert total == 2
    assert [i.id for i in items] == ["i2", "i1"]
    assert (await repo.list("u1", 2, 1))[0][0].id == "i1"
    assert await repo.list("u2", 1, 10) == ([], 0)
    await repo.add(_import(id="i3", user_id="u2"))  # same sha, other user is fine


async def test_duplicate_import_maps_to_domain_error(db):
    repo = MongoImportRepository(db)
    await repo.create_indexes()
    await repo.add(_import())
    with pytest.raises(DuplicateImport) as exc:
        await repo.add(_import(id="i-new", filename="copy.csv"))
    assert exc.value.import_id == "i1"


async def test_upsert_rejects_trade_without_natural_key(trades, make_trade):
    keyless = make_trade(position_id=None, row_hash=None)
    with pytest.raises(ValueError, match="position_id or row_hash"):
        await trades.upsert_many("u1", [keyless])


def _raw(ticket: int, position_id: int, **overrides) -> RawDeal:
    base = dict(
        ticket=ticket,
        position_id=position_id,
        time=T0 + timedelta(minutes=ticket),
        type=0,
        entry=0,
        symbol="EURUSD",
        volume=Decimal("0.10"),
        price=Decimal("1.12345"),
        commission=Decimal("-0.7"),
        swap=Decimal("0"),
        profit=Decimal("0"),
        sl=Decimal("1.1"),
        tp=None,
        comment="c",
        fee=Decimal("-0.05"),
    )
    base.update(overrides)
    return RawDeal(**base)


async def test_deals_upsert_is_idempotent_and_round_trips(db):
    deals = MongoDealRepository(db)
    await deals.create_indexes()
    batch = [_raw(1, 7), _raw(2, 7, entry=1, type=1), _raw(3, 8)]
    assert await deals.upsert_many("u1", "acc", batch) == 3
    assert await deals.upsert_many("u1", "acc", batch) == 0
    assert await db["deals"].count_documents({}) == 3

    got = await deals.positions_for("u1", "acc", [7])
    assert sorted(got, key=lambda d: d.ticket) == batch[:2]
    assert await deals.upsert_many("u1", "acc", []) == 0
    assert await deals.positions_for("u1", "acc", []) == []


async def test_deals_are_isolated_by_user_and_account(db):
    deals = MongoDealRepository(db)
    await deals.create_indexes()
    await deals.upsert_many("u1", "acc", [_raw(1, 7)])
    assert await deals.upsert_many("u2", "acc", [_raw(1, 7)]) == 1
    assert await deals.upsert_many("u1", "other", [_raw(1, 7)]) == 1
    assert len(await deals.positions_for("u1", "acc", [7])) == 1
    assert await deals.positions_for("u3", "acc", [7]) == []


async def test_deals_unique_index_rejects_duplicate_tickets(db):
    deals = MongoDealRepository(db)
    await deals.create_indexes()
    doc = {"user_id": "u1", "account_ref": "a", "ticket": 1}
    await db["deals"].insert_one(dict(doc))
    with pytest.raises(pymongo.errors.DuplicateKeyError):
        await db["deals"].insert_one(dict(doc))
