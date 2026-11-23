"""Parses every real report in ``data/private`` when present. Run with ``-m private``.

Files there are never committed (git-ignored). The test is deselected by default through
``addopts`` (``-m 'not private'``) and skipped when the folder is empty. It only prints
counts, never contents.
"""

from pathlib import Path

import pytest

from journal_service.adapters.outbound.parsers.dispatcher import DispatchingReportParser
from journal_service.adapters.outbound.parsers.flat_csv import FlatCsvParser
from journal_service.adapters.outbound.parsers.mt5_report import Mt5ReportParser

PRIVATE_DIR = Path(__file__).resolve().parents[4] / "data" / "private"
FILES = sorted(p for p in PRIVATE_DIR.glob("*") if p.is_file()) if PRIVATE_DIR.is_dir() else []

pytestmark = pytest.mark.private


@pytest.mark.skipif(not FILES, reason="no files in data/private")
@pytest.mark.parametrize("path", FILES, ids=[p.name for p in FILES])
def test_private_report_parses(path, capsys):
    parser = DispatchingReportParser([Mt5ReportParser(), FlatCsvParser()])

    report = parser.parse(path.name, path.read_bytes())

    with capsys.disabled():
        print(
            f"\n[private] {path.name}: account={'yes' if report.account else 'no'} "
            f"trades={len(report.trades)} balance_events={len(report.balance_events)} "
            f"skipped={len(report.skipped_rows)}"
        )
    assert report.trades
