from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol

from journal_service.domain.report_import import SkippedRow
from journal_service.domain.trade import Side


@dataclass(frozen=True)
class ReportAccount:
    login: str
    server: str
    currency: str | None = None


@dataclass(frozen=True)
class ParsedTrade:
    position_id: str | None
    symbol: str
    side: Side
    volume: Decimal
    open_time: datetime
    close_time: datetime
    open_price: Decimal
    close_price: Decimal
    stop_loss: Decimal | None
    take_profit: Decimal | None
    commission: Decimal
    swap: Decimal
    profit: Decimal
    comment: str | None


@dataclass(frozen=True)
class ParsedBalanceEvent:
    kind: Literal["deposit", "withdrawal", "credit"]
    amount: Decimal
    time: datetime
    source_ref: str
    comment: str | None


@dataclass(frozen=True)
class ParsedReport:
    account: ReportAccount | None
    trades: list[ParsedTrade] = field(default_factory=list)
    balance_events: list[ParsedBalanceEvent] = field(default_factory=list)
    skipped_rows: list[SkippedRow] = field(default_factory=list)


class ReportParser(Protocol):
    def parse(self, filename: str, content: bytes) -> ParsedReport:
        """Raise ``UnreadableReport`` when no recognizable trade table exists."""
        ...
