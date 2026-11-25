"""Shared helpers: reading raw rows, locating columns by header text, converting cell values."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import warnings
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import openpyxl

from journal_service.adapters.outbound.parsers.encoding import decode_text
from journal_service.application.ports.parsing import ParsedTrade
from journal_service.domain.errors import UnreadableReport
from journal_service.domain.report_import import SkippedRow
from journal_service.domain.trade import Side

Row = list[Any]

XLSX_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0"

# Header text (accents stripped, lowercase) -> canonical field. Duplicated Time/Price
# columns (MT5 positions) are resolved by order of appearance in ``map_columns``.
ALIASES = {
    "open time": "open_time", "opentime": "open_time", "open_time": "open_time",
    "hora de apertura": "open_time", "hora apertura": "open_time",
    "close time": "close_time", "closetime": "close_time", "close_time": "close_time",
    "hora de cierre": "close_time", "hora cierre": "close_time",
    "time": "time", "hora": "time", "tiempo": "time",
    "open price": "open_price", "openprice": "open_price", "open_price": "open_price",
    "precio de apertura": "open_price", "precio apertura": "open_price",
    "close price": "close_price", "closeprice": "close_price", "close_price": "close_price",
    "precio de cierre": "close_price", "precio cierre": "close_price",
    "price": "price", "precio": "price",
    "symbol": "symbol", "simbolo": "symbol",
    "type": "type", "tipo": "type", "order_type": "type", "ordertype": "type",
    "volume": "volume", "volumen": "volume", "lots": "volume", "lotes": "volume",
    "profit": "profit", "ganancias": "profit", "ganancia": "profit", "beneficio": "profit",
    "pnl": "profit", "profit_usd": "profit",
    "commission": "commission", "comision": "commission",
    "swap": "swap",
    "fee": "fee", "tarifa": "fee",
    "s / l": "stop_loss", "sl": "stop_loss", "s/l": "stop_loss",
    "t / p": "take_profit", "tp": "take_profit", "t/p": "take_profit",
    "comment": "comment", "comentario": "comment", "comente": "comment",
    "ticket": "position_id", "position": "position_id", "posicion": "position_id",
    "deal": "deal", "transaccion": "deal",
}  # fmt: skip

REQUIRED_TRADE_FIELDS = (
    "open_time", "close_time", "symbol", "type", "volume", "open_price", "close_price", "profit",
)  # fmt: skip

SIDE_WORDS = {
    "buy": Side.BUY, "compra": Side.BUY, "long": Side.BUY, "0": Side.BUY,
    "sell": Side.SELL, "venta": Side.SELL, "short": Side.SELL, "1": Side.SELL,
}  # fmt: skip

TIME_FORMATS = (
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
)


def normalize(text: Any) -> str:
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", stripped.replace("\xa0", " ")).strip().lower()


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    return isinstance(value, str) and not value.strip()


def clean_text(value: Any) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


# ---------------------------------------------------------------- reading raw rows


def is_xlsx(content: bytes) -> bool:
    return content[:4] == XLSX_MAGIC


def read_xlsx_rows(content: bytes) -> list[Row]:
    """``rows[i]`` is sheet row ``i + 1`` (leading empty rows included)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # openpyxl: "Workbook contains no default style"
            workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            sheet = workbook.worksheets[0]
            rows = [list(r) for r in sheet.iter_rows(min_row=1, min_col=1, values_only=True)]
    except Exception as exc:  # corrupt zip, not a workbook, ...
        raise UnreadableReport("the spreadsheet could not be opened") from exc
    return rows


def read_csv_rows(content: bytes, delimiter: str) -> list[Row]:
    """``rows[i]`` is the record starting on text line ``i + 1``.

    A record spanning several lines (quoted newline) is followed by empty filler rows, so later
    records keep their line numbers; empty rows are skipped by every table reader.
    """
    text = decode_text(content)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: list[Row] = []
    for record in reader:
        rows.append(list(record))
        rows.extend([] for _ in range(reader.line_num - len(rows)))
    return rows


# ------------------------------------------------------------------ columns


def map_columns(cells: Row) -> dict[str, int]:
    """Map canonical field -> column index for one candidate header row."""
    mapping: dict[str, int] = {}
    seen_time = seen_price = 0
    for index, cell in enumerate(cells):
        if is_blank(cell):
            continue
        field = ALIASES.get(normalize(cell))
        if field == "time":
            seen_time += 1
            field = {1: "open_time", 2: "close_time"}.get(seen_time)
        elif field == "price":
            seen_price += 1
            field = {1: "open_price", 2: "close_price"}.get(seen_price)
        if field is not None and field not in mapping:
            mapping[field] = index
    return mapping


def find_trade_header(rows: list[Row], start: int = 0) -> tuple[int, dict[str, int]] | None:
    for index in range(start, len(rows)):
        mapping = map_columns(rows[index])
        if all(f in mapping for f in REQUIRED_TRADE_FIELDS):
            return index, mapping
    return None


def cell(row: Row, mapping: dict[str, int], field: str) -> Any:
    index = mapping.get(field)
    if index is None or index >= len(row):
        return None
    return row[index]


# ------------------------------------------------------------------ values


class BadValue(ValueError):
    """A cell could not be converted."""


def _is_grouped(text: str, sep: str) -> bool:
    return re.fullmatch(r"\d{1,3}(?:" + re.escape(sep) + r"\d{3})+", text) is not None


def _locale_text(raw: str, value: Any) -> str:
    """Normalize a locale-formatted number to plain ``-1234.56`` text, or raise ``BadValue``.

    Whitespace/NBSP are thousands separators. With both "." and "," the last one is the decimal
    separator and the other must be valid grouping. A lone "," followed by exactly three digits
    is ambiguous ("1,234" vs "1,234 as decimal") and is never guessed.
    """
    text = re.sub(r"\s+", "", raw.replace(" ", " "))
    sign = ""
    if text[:1] in "+-":
        sign, text = text[0], text[1:]
    if not re.fullmatch(r"[\d.,]+", text):
        return sign + text  # let Decimal decide (e.g. exponent notation) or reject
    bad = BadValue(f"not a number: {str(value)[:30]!r}")
    if "," in text and "." in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        group_sep = "." if decimal_sep == "," else ","
        integer, _, fraction = text.rpartition(decimal_sep)
        if not (integer.isdigit() or _is_grouped(integer, group_sep)):
            raise bad
        return f"{sign}{integer.replace(group_sep, '')}.{fraction}"
    if "," in text:
        if text.count(",") > 1:
            if not _is_grouped(text, ","):
                raise bad
            return sign + text.replace(",", "")
        integer, _, fraction = text.partition(",")
        if len(fraction) == 3:
            raise BadValue(f"ambiguous number format: {str(value)[:30]}")
        return f"{sign}{integer}.{fraction}"
    return sign + text


def to_decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or is_blank(value):
        raise BadValue(f"{label} is missing")
    try:
        text = repr(value) if isinstance(value, int | float) else _locale_text(str(value), value)
        number = Decimal(text)
    except BadValue as exc:
        raise BadValue(f"{label}: {exc}" if "ambiguous" not in str(exc) else str(exc)) from None
    except InvalidOperation:
        raise BadValue(f"{label} is not a number: {str(value)[:30]!r}") from None
    if not number.is_finite():
        raise BadValue(f"{label} is not a number: {str(value)[:30]!r}")
    return number


def to_optional_decimal(value: Any, label: str) -> Decimal | None:
    return None if is_blank(value) else to_decimal(value, label)


def to_time(value: Any, label: str) -> datetime:
    """Report times are naive broker times, taken as UTC (offset handling arrives in plan 3)."""
    if isinstance(value, datetime):
        parsed = value
    elif is_blank(value):
        raise BadValue(f"{label} is missing")
    else:
        text = str(value).strip()
        parsed = None
        for fmt in TIME_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                raise BadValue(f"{label} is not a date: {text[:30]!r}") from None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def to_side(value: Any) -> Side | None:
    text = clean_text(value)
    return None if text is None else SIDE_WORDS.get(normalize(text))


def zero_to_none(value: Decimal | None) -> Decimal | None:
    return None if value is None or value == 0 else value


# ------------------------------------------------------------------ trade rows


def parse_trade_row(row: Row, mapping: dict[str, int], row_number: int) -> ParsedTrade | SkippedRow:
    """Convert one table row; any problem yields a ``SkippedRow`` with a reason."""
    try:
        side = to_side(cell(row, mapping, "type"))
        if side is None:
            return SkippedRow(
                row_number, f"unsupported type: {str(cell(row, mapping, 'type'))[:20]!r}"
            )
        symbol = clean_text(cell(row, mapping, "symbol"))
        if symbol is None:
            return SkippedRow(row_number, "symbol is missing")
        volume = to_decimal(cell(row, mapping, "volume"), "volume")
        open_time = to_time(cell(row, mapping, "open_time"), "open time")
        close_time = to_time(cell(row, mapping, "close_time"), "close time")
        open_price = to_decimal(cell(row, mapping, "open_price"), "open price")
        close_price = to_decimal(cell(row, mapping, "close_price"), "close price")
        profit = to_decimal(cell(row, mapping, "profit"), "profit")
        commission = to_optional_decimal(cell(row, mapping, "commission"), "commission")
        swap = to_optional_decimal(cell(row, mapping, "swap"), "swap")
        stop_loss = zero_to_none(to_optional_decimal(cell(row, mapping, "stop_loss"), "stop loss"))
        take_profit = zero_to_none(
            to_optional_decimal(cell(row, mapping, "take_profit"), "take profit")
        )
    except BadValue as exc:
        return SkippedRow(row_number, str(exc))
    if close_time < open_time:
        return SkippedRow(row_number, "close time is before open time")
    return ParsedTrade(
        position_id=clean_text(cell(row, mapping, "position_id")),
        symbol=symbol,
        side=side,
        volume=volume,
        open_time=open_time,
        close_time=close_time,
        open_price=open_price,
        close_price=close_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        commission=commission if commission is not None else Decimal(0),
        swap=swap if swap is not None else Decimal(0),
        profit=profit,
        comment=clean_text(cell(row, mapping, "comment")),
    )


SECTION_LABELS = {
    "positions", "orders", "deals", "results", "open positions", "working orders", "summary",
    "posiciones", "ordenes", "transacciones", "operaciones", "resultados", "posiciones abiertas",
}  # fmt: skip


def is_blank_row(row: Row) -> bool:
    return all(is_blank(v) for v in row)


def is_section_label(row: Row) -> bool:
    """A lone section label ("Orders", "Deals", ...) ends a table; blank rows never do."""
    filled = [v for v in row if not is_blank(v)]
    return len(filled) == 1 and normalize(filled[0]) in SECTION_LABELS


def read_trade_table(
    rows: list[Row], header_index: int, mapping: dict[str, int]
) -> tuple[list[ParsedTrade], list[SkippedRow]]:
    """Skipped rows carry the absolute 1-based sheet/file row, as a user sees it."""
    trades: list[ParsedTrade] = []
    skipped: list[SkippedRow] = []
    # rows[i] is sheet/file row i + 1, so the first data row is header_index + 2.
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if is_blank_row(row):
            continue  # blank rows inside a table are skipped, never a reason to stop
        if is_section_label(row):
            break
        if is_blank(cell(row, mapping, "open_time")) and is_blank(cell(row, mapping, "symbol")):
            if is_blank(cell(row, mapping, "type")):
                continue  # totals line (only commission/swap/profit filled)
            skipped.append(SkippedRow(row_number, "time and symbol are missing"))
            continue
        result = parse_trade_row(row, mapping, row_number)
        if isinstance(result, SkippedRow):
            skipped.append(result)
        else:
            trades.append(result)
    return trades, skipped
