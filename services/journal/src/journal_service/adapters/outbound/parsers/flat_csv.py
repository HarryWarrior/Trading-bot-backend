"""One-table CSV/XLSX exports with English or Spanish headers (also bare MT5 position tables)."""

from __future__ import annotations

from journal_service.adapters.outbound.parsers._table import (
    OLE_MAGIC,
    Row,
    find_trade_header,
    is_xlsx,
    read_csv_rows,
    read_trade_table,
    read_xlsx_rows,
)
from journal_service.application.ports.parsing import ParsedReport
from journal_service.domain.errors import UnreadableReport

DELIMITERS = (",", ";", "\t")


class FlatCsvParser:
    def accepts(self, filename: str, content: bytes) -> bool:
        try:
            self._locate(content)
        except UnreadableReport:
            return False
        return True

    def parse(self, filename: str, content: bytes) -> ParsedReport:
        rows, (header_index, mapping) = self._locate(content)
        trades, skipped = read_trade_table(rows, header_index, mapping)
        return ParsedReport(account=None, trades=trades, skipped_rows=skipped)

    @staticmethod
    def _locate(content: bytes) -> tuple[list[Row], tuple[int, dict[str, int]]]:
        if content[:4] == OLE_MAGIC:
            raise UnreadableReport("legacy .xls files are not supported; save as .xlsx or .csv")
        if is_xlsx(content):
            candidates = [read_xlsx_rows(content)]
        else:
            candidates = [read_csv_rows(content, d) for d in DELIMITERS]
        for rows in candidates:
            found = find_trade_header(rows)
            if found is not None:
                return rows, found
        raise UnreadableReport("no trade table found (expected columns such as Time, Symbol, Type)")
