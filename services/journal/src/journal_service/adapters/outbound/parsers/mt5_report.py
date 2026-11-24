"""MT5 Trade History Report workbooks: header block, Positions and Deals sections."""

from __future__ import annotations

import re
from decimal import Decimal

from journal_service.adapters.outbound.parsers._table import (
    BadValue,
    Row,
    cell,
    clean_text,
    find_trade_header,
    is_blank,
    is_blank_row,
    is_section_label,
    is_xlsx,
    map_columns,
    normalize,
    read_trade_table,
    read_xlsx_rows,
    to_decimal,
    to_optional_decimal,
    to_time,
)
from journal_service.application.ports.parsing import (
    ParsedBalanceEvent,
    ParsedReport,
    ReportAccount,
)
from journal_service.domain.errors import UnreadableReport
from journal_service.domain.report_import import SkippedRow

POSITIONS_LABELS = {"positions", "posiciones"}
DEALS_LABELS = {"deals", "transacciones", "operaciones"}
ACCOUNT_LABELS = {"account:", "cuenta:"}
ACCOUNT_PATTERN = re.compile(r"^\s*(\d+)\s*\(([^,)]*),\s*([^,)]*)")
BALANCE_WORDS = {"balance", "saldo"}
CREDIT_WORDS = {"credit", "credito"}
# Trade deals are covered by the Positions section and ignored here.
TRADE_DEAL_WORDS = {
    "buy", "sell", "compra", "venta", "buy canceled", "sell canceled",
    "compra cancelada", "venta cancelada",
}  # fmt: skip
# Non-trade deals that change the balance (first word of the type, accents stripped), e.g.
# "correction", "charge", "bonus", "commission daily", "interest", "dividend franked", "tax".
ADJUSTMENT_WORDS = {
    "correction", "charge", "bonus", "commission", "fee", "interest", "dividend", "tax",
    "correccion", "cargo", "bono", "bonificacion", "comision", "tarifa", "interes",
    "dividendo", "impuesto",
}  # fmt: skip
ADJUSTMENT_AMOUNT_COLUMNS = ("profit", "commission", "fee", "swap")


def _section_start(rows: list[Row], labels: set[str]) -> int | None:
    for index, row in enumerate(rows):
        filled = [v for v in row if not is_blank(v)]
        if len(filled) == 1 and normalize(filled[0]) in labels:
            return index
    return None


def _account(rows: list[Row], limit: int) -> ReportAccount | None:
    for row in rows[:limit]:
        if not row or is_blank(row[0]) or normalize(row[0]) not in ACCOUNT_LABELS:
            continue
        for value in row[1:]:
            match = None if is_blank(value) else ACCOUNT_PATTERN.match(str(value))
            if match:
                login, currency, server = (g.strip() for g in match.groups())
                return ReportAccount(login=login, server=server, currency=currency or None)
    return None


def _adjustment_amount(row: Row, mapping: dict[str, int]) -> Decimal:
    """Profit + Commission + Fee + Swap: brokers put the amount of a commission, fee or
    interest deal in different columns. Blank cells count as 0; all blank is an error."""
    values = [
        to_optional_decimal(cell(row, mapping, column), column)
        for column in ADJUSTMENT_AMOUNT_COLUMNS
    ]
    present = [v for v in values if v is not None]
    if not present:
        raise BadValue("amount is missing")
    return sum(present, Decimal(0))


class Mt5ReportParser:
    def accepts(self, filename: str, content: bytes) -> bool:
        if not is_xlsx(content):
            return False
        try:
            return _section_start(read_xlsx_rows(content), POSITIONS_LABELS) is not None
        except UnreadableReport:
            return False

    def parse(self, filename: str, content: bytes) -> ParsedReport:
        rows = read_xlsx_rows(content)
        positions_at = _section_start(rows, POSITIONS_LABELS)
        if positions_at is None:
            raise UnreadableReport("no Positions section found in the report")
        header = find_trade_header(rows, positions_at + 1)
        if header is None:
            raise UnreadableReport("the Positions section has no recognizable header row")
        trades, skipped = read_trade_table(rows, *header)
        events, balance_skipped = self._balance_events(rows)
        return ParsedReport(
            account=_account(rows, positions_at),
            trades=trades,
            balance_events=events,
            skipped_rows=skipped + balance_skipped,
        )

    @staticmethod
    def _balance_events(rows: list[Row]) -> tuple[list[ParsedBalanceEvent], list[SkippedRow]]:
        deals_at = _section_start(rows, DEALS_LABELS)
        if deals_at is None:
            return [], []
        needed = {"open_time", "deal", "type", "profit"}
        header_index = next(
            (i for i in range(deals_at + 1, len(rows)) if needed <= map_columns(rows[i]).keys()),
            None,
        )
        if header_index is None:
            return [], []
        mapping = map_columns(rows[header_index])
        events: list[ParsedBalanceEvent] = []
        skipped: list[SkippedRow] = []
        # rows[i] is sheet row i + 1: skipped rows report the sheet row a user sees.
        for deal_row, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            if is_blank_row(row):
                continue
            if is_section_label(row):
                break
            type_cell = cell(row, mapping, "type")
            if is_blank(type_cell):
                continue  # totals line: no deal type, no information of its own
            kind_word = normalize(type_cell)
            if kind_word in TRADE_DEAL_WORDS:
                continue  # trade deals are covered by the Positions section
            is_adjustment = kind_word.split(" ")[0] in ADJUSTMENT_WORDS
            if not is_adjustment and kind_word not in BALANCE_WORDS | CREDIT_WORDS:
                # Dropping it silently would change the balance used for drawdown.
                skipped.append(
                    SkippedRow(deal_row, f"unsupported balance deal type '{clean_text(type_cell)}'")
                )
                continue
            ticket = clean_text(cell(row, mapping, "deal"))
            try:
                if ticket is None:
                    raise BadValue("deal ticket is missing")
                amount = (
                    _adjustment_amount(row, mapping)
                    if is_adjustment
                    else to_decimal(cell(row, mapping, "profit"), "amount")
                )
                time = to_time(cell(row, mapping, "open_time"), "time")
            except BadValue as exc:
                # Dropping it silently would change the balance used for drawdown.
                skipped.append(SkippedRow(deal_row, f"balance row in Deals section: {exc}"))
                continue
            if amount == Decimal(0):
                continue  # zero-amount balance rows carry no information; ignored on purpose
            if is_adjustment:
                kind = "adjustment"
            elif kind_word in CREDIT_WORDS:
                kind = "credit"
            else:
                kind = "deposit" if amount > 0 else "withdrawal"
            events.append(
                ParsedBalanceEvent(
                    kind=kind,
                    amount=amount,
                    time=time,
                    source_ref=ticket,
                    comment=clean_text(cell(row, mapping, "comment")),
                )
            )
        return events, skipped
