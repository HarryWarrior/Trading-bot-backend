"""Picks the first parser that recognizes the file."""

from __future__ import annotations

from typing import Protocol

from journal_service.application.ports.parsing import ParsedReport
from journal_service.domain.errors import UnreadableReport


class AcceptingParser(Protocol):
    def accepts(self, filename: str, content: bytes) -> bool: ...

    def parse(self, filename: str, content: bytes) -> ParsedReport: ...


class DispatchingReportParser:
    def __init__(self, parsers: list[AcceptingParser]) -> None:
        self._parsers = list(parsers)

    def parse(self, filename: str, content: bytes) -> ParsedReport:
        for parser in self._parsers:
            if parser.accepts(filename, content):
                return parser.parse(filename, content)
        raise UnreadableReport("unrecognized format")
