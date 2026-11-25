from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from report_builders import (
    balance_deal,
    build_flat_xlsx,
    build_mt5_xlsx,
    csv_bytes,
    money_deal,
)

from journal_service.adapters.outbound.parsers.dispatcher import DispatchingReportParser
from journal_service.adapters.outbound.parsers.encoding import decode_text
from journal_service.adapters.outbound.parsers.flat_csv import FlatCsvParser
from journal_service.adapters.outbound.parsers.mt5_report import Mt5ReportParser
from journal_service.domain.errors import UnreadableReport
from journal_service.domain.trade import Side

SAMPLE_CSV = Path(__file__).resolve().parents[4] / "data" / "samples" / "sample_trades.csv"
FLAT_HEADER = "Open Time,Close Time,Symbol,Type,Volume,Open Price,Close Price,Profit,Comment\n"


@pytest.fixture
def parser() -> DispatchingReportParser:
    return DispatchingReportParser([Mt5ReportParser(), FlatCsvParser()])


def test_mt5_xlsx_positions_and_balance(parser):
    report = parser.parse("report.xlsx", build_mt5_xlsx())

    assert report.account is not None
    assert (report.account.login, report.account.server, report.account.currency) == (
        "12345678",
        "Demo-Server",
        "USD",
    )
    assert [t.position_id for t in report.trades] == ["1001", "1002", "1003"]
    first = report.trades[0]
    assert first.side is Side.SELL
    assert first.volume == Decimal("0.06")
    assert first.open_price == Decimal("4800.50")
    assert first.stop_loss == Decimal("4810.00")
    assert first.take_profit is None  # 0.00 means "not set"
    assert first.commission == Decimal("-1.20")
    assert first.profit == Decimal("60.00")
    assert first.open_time == datetime(2026, 1, 22, 15, 55, 8, tzinfo=UTC)
    assert first.close_time == datetime(2026, 1, 22, 16, 32, 0, tzinfo=UTC)
    assert report.trades[2].profit == Decimal("-30.00")
    assert [(e.kind, e.amount, e.source_ref) for e in report.balance_events] == [
        ("deposit", Decimal("10000.00"), "1"),
        ("withdrawal", Decimal("-500.00"), "2"),
    ]
    assert report.skipped_rows == []


def test_mt5_account_summary_block_ends_the_deals_table(parser):
    # build_mt5_xlsx emits the Deals totals line and the Balance:/Credit Facility:/
    # Floating P/L:/Equity: block before "Results", as real reports do.
    report = parser.parse("report.xlsx", build_mt5_xlsx())

    assert report.skipped_rows == []
    assert [(e.kind, e.amount) for e in report.balance_events] == [
        ("deposit", Decimal("10000.00")),
        ("withdrawal", Decimal("-500.00")),
    ]


def test_mt5_report_ignores_orders_and_results_sections(parser):
    report = parser.parse("report.xlsx", build_mt5_xlsx())

    assert len(report.trades) == 3  # the Orders section has other rows with buy/sell types
    assert all(t.position_id in {"1001", "1002", "1003"} for t in report.trades)


def test_mt5_credit_rows_become_credit_events(parser):
    deals = [balance_deal("2026.01.20 08:00:00", "7", "250.00", "250.00", kind="credit")]

    report = parser.parse("r.xlsx", build_mt5_xlsx(deals=deals))

    assert [(e.kind, e.amount) for e in report.balance_events] == [("credit", Decimal("250.00"))]


def test_mt5_adjustment_deals_become_signed_adjustment_events(parser):
    deals = [
        balance_deal("2026.01.20 08:00:00", "1", "1 000.00", "1 000.00"),
        money_deal("2026.01.21 08:00:00", "2", "correction", profit="25.00"),
        money_deal("2026.01.21 09:00:00", "3", "charge", profit="-10.00"),
        money_deal("2026.01.21 10:00:00", "4", "commission daily", commission="-3.50"),
        money_deal("2026.01.21 11:00:00", "5", "bonus", profit="100.00", comment="Promo"),
        money_deal("2026.01.21 12:00:00", "6", "interest", profit="1.00", swap="-0.25"),
        money_deal("2026.01.21 13:00:00", "7", "dividend", profit="0.00"),
        money_deal("2026.01.21 14:00:00", "8", "tax", fee="-2.00"),
        ["2026.01.22 15:55:08", "9", "XAUUSD", "buy", "in", "0.06", "4 800.50", "9", "-1.20",
         "0", "0", "0.00", "", ""],
    ]  # fmt: skip

    report = parser.parse("r.xlsx", build_mt5_xlsx(deals=deals))

    assert [(e.kind, e.amount, e.source_ref) for e in report.balance_events] == [
        ("deposit", Decimal("1000.00"), "1"),
        ("adjustment", Decimal("25.00"), "2"),
        ("adjustment", Decimal("-10.00"), "3"),
        ("adjustment", Decimal("-3.50"), "4"),
        ("adjustment", Decimal("100.00"), "5"),
        ("adjustment", Decimal("0.75"), "6"),
        ("adjustment", Decimal("-2.00"), "8"),
    ]  # zero-amount dividend ignored; the buy deal is covered by Positions
    assert report.balance_events[4].comment == "Promo"
    assert report.skipped_rows == []


def test_mt5_spanish_adjustment_deals(parser):
    deals = [
        money_deal("2026.01.21 08:00:00", "2", "Corrección", profit="5.00"),
        money_deal("2026.01.21 09:00:00", "3", "Comisión", commission="-1.00"),
    ]

    report = parser.parse("r.xlsx", build_mt5_xlsx(deals=deals))

    assert [(e.kind, e.amount) for e in report.balance_events] == [
        ("adjustment", Decimal("5.00")),
        ("adjustment", Decimal("-1.00")),
    ]


def test_mt5_unknown_non_trade_deal_type_is_reported(parser):
    deals = [money_deal("2026.01.21 08:00:00", "2", "Mystery Thing", profit="5.00")]

    report = parser.parse("r.xlsx", build_mt5_xlsx(deals=deals))

    assert report.balance_events == []
    assert [(s.row, s.reason) for s in report.skipped_rows] == [
        (20, "unsupported balance deal type 'Mystery Thing'")  # first Deals row is sheet row 20
    ]


def test_mt5_adjustment_without_any_amount_is_reported(parser):
    deals = [money_deal("2026.01.21 08:00:00", "2", "correction")]

    report = parser.parse("r.xlsx", build_mt5_xlsx(deals=deals))

    assert report.balance_events == []
    assert len(report.skipped_rows) == 1
    assert "amount is missing" in report.skipped_rows[0].reason


def test_mt5_report_without_account_line_has_no_account(parser):
    report = parser.parse("r.xlsx", build_mt5_xlsx(account=None))

    assert report.account is None
    assert len(report.trades) == 3


def test_sample_csv_parses_10_trades(parser):
    report = parser.parse("sample_trades.csv", SAMPLE_CSV.read_bytes())

    assert report.account is None
    assert len(report.trades) == 10
    assert sum(t.profit for t in report.trades) == Decimal("1450")
    assert report.skipped_rows == []
    assert all(t.open_time.tzinfo is UTC for t in report.trades)


def test_spanish_headers(parser):
    text = (
        "Hora de apertura,Hora de cierre,Símbolo,Tipo,Volumen,Precio de apertura,"
        "Precio de cierre,Ganancias,Comentario\n"
        "2025-03-01 10:00:00,2025-03-01 11:00:00,EURUSD,compra,0.5,1.1000,1.1020,100.5,uno\n"
        "2025-03-02 10:00:00,2025-03-02 11:00:00,EURUSD,venta,0.5,1.1000,1.1020,-40,\n"
    )

    report = parser.parse("es.csv", csv_bytes(text))

    assert [t.side for t in report.trades] == [Side.BUY, Side.SELL]
    assert report.trades[0].profit == Decimal("100.5")
    assert report.trades[0].comment == "uno"
    assert report.trades[1].comment is None


def test_spanish_mt5_report_headers(parser):
    report = parser.parse("es.xlsx", build_mt5_xlsx(spanish=True))

    assert len(report.trades) == 3
    assert report.trades[0].symbol == "XAUUSD"


def test_utf16_csv_is_decoded(parser):
    text = FLAT_HEADER + "2025-03-01 10:00:00,2025-03-01 11:00:00,EURUSD,BUY,1,1.1,1.2,10,café\n"

    report = parser.parse("mt5.csv", text.encode("utf-16"))

    assert len(report.trades) == 1
    assert report.trades[0].comment == "café"


def test_decode_text_falls_back_to_cp1252():
    assert decode_text("preço".encode("cp1252")) == "preço"
    assert decode_text(b"\xef\xbb\xbfabc") == "abc"


def test_malformed_row_is_skipped_with_reason(parser):
    text = (
        FLAT_HEADER
        + "2025-03-01 10:00:00,2025-03-01 11:00:00,EURUSD,BUY,1,1.1,1.2,10,\n"
        + "2025-03-02 10:00:00,2025-03-02 11:00:00,EURUSD,BUY,1,1.1,1.2,abc,\n"
        + "2025-03-03 10:00:00,2025-03-03 11:00:00,EURUSD,SELL,1,1.2,1.1,20,\n"
    )

    report = parser.parse("x.csv", csv_bytes(text))

    assert [t.profit for t in report.trades] == [Decimal("10"), Decimal("20")]
    assert len(report.skipped_rows) == 1
    assert report.skipped_rows[0].row == 3  # file line: header is line 1
    assert "profit" in report.skipped_rows[0].reason.lower()


def test_close_before_open_is_skipped(parser):
    text = FLAT_HEADER + "2025-03-01 12:00:00,2025-03-01 11:00:00,EURUSD,BUY,1,1.1,1.2,10,\n"

    report = parser.parse("x.csv", csv_bytes(text))

    assert report.trades == []
    assert report.skipped_rows[0].row == 2
    assert "before" in report.skipped_rows[0].reason


def test_mt5_non_trade_type_in_positions_is_skipped(parser):
    positions = [
        [
            "2026.01.23 09:00:00", "5", "EURUSD", "weird", "0.10", "1.1", "0", "0",
            "2026.01.23 10:00:00", "1.2", "0", "0", "5",
        ],
        [
            "2026.01.23 09:00:00", "6", "EURUSD", "BUY", "0.10", "1.1", "0", "0",
            "2026.01.23 10:00:00", "1.2", "0", "0", "5",
        ],
    ]  # fmt: skip

    report = parser.parse("r.xlsx", build_mt5_xlsx(positions=positions))

    assert [t.position_id for t in report.trades] == ["6"]
    assert report.skipped_rows[0].row == 8  # sheet row: 5 header lines, "Positions", header


def test_ticket_column_becomes_position_id(parser):
    text = (
        "Ticket, Open Time, Symbol, Volume, Type, Open Price, Close Time, Close Price,"
        " Profit, Status\n"
        "39389,2025-05-28 14:08:59,XAUUSD,0.01,1,3306,2025-05-28 16:15:31,3297,8.58,CLOSED\n"
        "39394,2025-05-28 14:11:23,XAUUSD,0.06,0,3305,2025-05-28 16:15:29,3297,-4,CLOSED\n"
    )

    report = parser.parse("t.csv", csv_bytes(text))

    assert [t.position_id for t in report.trades] == ["39389", "39394"]
    assert [t.side for t in report.trades] == [Side.SELL, Side.BUY]


def test_flat_xlsx_with_leading_title_rows(parser):
    header = [
        "Open Time", "Close Time", "Symbol", "Type", "Volume", "Open Price", "Close Price", "Profit",
    ]  # fmt: skip
    rows = [["2025-03-01 10:00:00", "2025-03-01 11:00:00", "EURUSD", "buy", 1, 1.1, 1.2, 10.5]]

    report = parser.parse("flat.xlsx", build_flat_xlsx(rows, header))

    assert len(report.trades) == 1
    assert report.trades[0].profit == Decimal("10.5")


@pytest.mark.parametrize(
    "content",
    [b"just some text, nothing tabular\nat all\n", b"\x00\x01\x02\x03binary", b"", b"PKnot a zip"],
)
def test_unrecognized_file_raises_unreadable_report(parser, content):
    with pytest.raises(UnreadableReport):
        parser.parse("mystery.csv", content)


def test_dispatcher_with_no_parsers_raises_unrecognized_format():
    with pytest.raises(UnreadableReport, match="unrecognized format"):
        DispatchingReportParser([]).parse("a.csv", b"x")


def _flat_with_number(column_value: str, column: str = "volume"):
    base = {"volume": "1", "open": "1.1", "close": "1.2", "profit": "10"}
    base[column] = f'"{column_value}"'
    return (
        FLAT_HEADER
        + f"2025-03-01 10:00:00,2025-03-01 11:00:00,EURUSD,BUY,{base['volume']},"
        + f"{base['open']},{base['close']},{base['profit']},\n"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1,234.56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("1,5", "1.5"),
        ("12,34", "12.34"),
        ("1,234,567.8", "1234567.8"),
        ("3 328.61", "3328.61"),
        ("- 30.12", "-30.12"),
        ("3\u00a0328,61", "3328.61"),
    ],
)
def test_locale_numbers_are_parsed_exactly(parser, text, expected):
    report = parser.parse("n.csv", csv_bytes(_flat_with_number(text, "profit")))

    assert [t.profit for t in report.trades] == [Decimal(expected)]


@pytest.mark.parametrize("text", ["0,001", "1,234", "150,123"])
def test_ambiguous_numbers_are_skipped_never_guessed(parser, text):
    report = parser.parse("n.csv", csv_bytes(_flat_with_number(text)))

    assert report.trades == []
    assert report.skipped_rows[0].reason == f"ambiguous number format: {text}"


def test_invalid_grouping_is_unparseable(parser):
    report = parser.parse("n.csv", csv_bytes(_flat_with_number("1.2,3,4", "profit")))

    assert report.trades == []
    assert len(report.skipped_rows) == 1


def test_blank_line_inside_flat_table_does_not_drop_later_trades(parser):
    rows = [
        f"2025-03-0{d} 10:00:00,2025-03-0{d} 11:00:00,EURUSD,BUY,1,1.1,1.2,{d},\n"
        for d in range(1, 10)
    ]
    text = (
        FLAT_HEADER
        + "".join(rows[:5])
        + "\n"
        + "".join(rows[5:])
        + ("2025-03-10 10:00:00,2025-03-10 11:00:00,EURUSD,BUY,1,1.1,1.2,10,\n")
    )

    report = parser.parse("gap.csv", csv_bytes(text))

    assert len(report.trades) == 10
    assert report.skipped_rows == []


def test_unparseable_balance_rows_are_reported_not_dropped(parser):
    deals = [
        balance_deal("2026.01.20 08:00:00", "1", "10 000.00", "10 000.00"),
        balance_deal("2026.01.21 08:00:00", "2", "abc", "0"),
        balance_deal("not a time", "3", "5.00", "0"),
        balance_deal("2026.01.22 08:00:00", "", "5.00", "0"),
        balance_deal("2026.01.23 08:00:00", "5", "0.00", "0"),
    ]

    report = parser.parse("r.xlsx", build_mt5_xlsx(deals=deals))

    assert [e.source_ref for e in report.balance_events] == ["1"]
    assert len(report.skipped_rows) == 3  # zero-amount row is ignored on purpose
    assert [s.row for s in report.skipped_rows] == [21, 22, 23]  # sheet rows
    assert all("balance row" in s.reason for s in report.skipped_rows)


def test_xlsx_bytes_with_csv_filename_are_parsed(parser):
    report = parser.parse("renamed.csv", build_mt5_xlsx())

    assert len(report.trades) == 3
    assert report.account is not None


def test_skipped_row_numbers_count_blank_lines(parser):
    good = "2025-03-01 10:00:00,2025-03-01 11:00:00,EURUSD,BUY,1,1.1,1.2,10,\n"
    bad = "2025-03-02 10:00:00,2025-03-02 11:00:00,EURUSD,BUY,1,1.1,1.2,abc,\n"
    text = FLAT_HEADER + good + "\n\n" + bad

    report = parser.parse("x.csv", csv_bytes(text))

    assert [s.row for s in report.skipped_rows] == [5]


def test_skipped_row_numbers_count_lines_of_multiline_fields(parser):
    multiline = '2025-03-01 10:00:00,2025-03-01 11:00:00,EURUSD,BUY,1,1.1,1.2,10,"a\nb"\n'
    bad = "2025-03-02 10:00:00,2025-03-02 11:00:00,EURUSD,BUY,1,1.1,1.2,abc,\n"
    text = FLAT_HEADER + multiline + bad

    report = parser.parse("x.csv", csv_bytes(text))

    assert len(report.trades) == 1
    assert [s.row for s in report.skipped_rows] == [4]


def test_skipped_row_numbers_are_sheet_rows_in_flat_xlsx(parser):
    header = ["Open Time", "Close Time", "Symbol", "Type", "Volume", "Open Price",
              "Close Price", "Profit"]  # fmt: skip
    rows = [
        ["2025-03-01 10:00:00", "2025-03-01 11:00:00", "EURUSD", "BUY", "1", "1.1", "1.2", "10"],
        ["2025-03-02 10:00:00", "2025-03-02 11:00:00", "EURUSD", "BUY", "1", "1.1", "1.2", "x"],
    ]

    report = parser.parse("t.xlsx", build_flat_xlsx(rows, header))

    assert [s.row for s in report.skipped_rows] == [5]  # title row 1, header row 3


def test_skipped_row_numbers_count_leading_empty_sheet_rows(parser):
    header = ["Open Time", "Close Time", "Symbol", "Type", "Volume", "Open Price",
              "Close Price", "Profit"]  # fmt: skip
    bad = ["2025-03-02 10:00:00", "2025-03-02 11:00:00", "EURUSD", "BUY", "1", "1.1", "1.2", "x"]

    content = build_flat_xlsx([bad], header, title=False)

    assert [s.row for s in parser.parse("t.xlsx", content).skipped_rows] == [4]
