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
    is_table_end,
    is_xlsx,
    map_columns,
    normalize,
    read_trade_table,
    read_xlsx_rows,
    to_decimal,
    to_time,
)
from journal_service.application.ports.parsing import (
    ParsedBalanceEvent,
    ParsedReport,
    ReportAccount,
)
from journal_service.domain.errors import UnreadableReport

POSITIONS_LABELS = {"positions", "posiciones"}
DEALS_LABELS = {"deals", "transacciones", "operaciones"}
ACCOUNT_LABELS = {"account:", "cuenta:"}
ACCOUNT_PATTERN = re.compile(r"^\s*(\d+)\s*\(([^,)]*),\s*([^,)]*)")
BALANCE_WORDS = {"balance", "saldo"}
CREDIT_WORDS = {"credit", "credito"}


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
        return ParsedReport(
            account=_account(rows, positions_at),
            trades=trades,
            balance_events=self._balance_events(rows),
            skipped_rows=skipped,
        )

    @staticmethod
    def _balance_events(rows: list[Row]) -> list[ParsedBalanceEvent]:
        deals_at = _section_start(rows, DEALS_LABELS)
        if deals_at is None:
            return []
        needed = {"open_time", "deal", "type", "profit"}
        header_index = next(
            (i for i in range(deals_at + 1, len(rows)) if needed <= map_columns(rows[i]).keys()),
            None,
        )
        if header_index is None:
            return []
        mapping = map_columns(rows[header_index])
        events: list[ParsedBalanceEvent] = []
        for row in rows[header_index + 1 :]:
            if is_table_end(row):
                break
            type_cell = cell(row, mapping, "type")
            kind_word = "" if is_blank(type_cell) else normalize(type_cell)
            if kind_word not in BALANCE_WORDS | CREDIT_WORDS:
                continue
            ticket = clean_text(cell(row, mapping, "deal"))
            try:
                amount = to_decimal(cell(row, mapping, "profit"), "amount")
                time = to_time(cell(row, mapping, "open_time"), "time")
            except BadValue:
                continue
            if ticket is None or amount == Decimal(0):
                continue
            if kind_word in CREDIT_WORDS:
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
        return events
