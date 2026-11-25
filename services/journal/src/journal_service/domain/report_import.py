from dataclasses import dataclass, field
from datetime import datetime

from journal_service.domain.trade import require_aware


@dataclass(frozen=True)
class SkippedRow:
    row: int
    reason: str


@dataclass(frozen=True)
class ReportImport:
    id: str
    user_id: str
    filename: str
    sha256: str
    account_ref: str
    trades_created: int
    trades_updated: int
    balance_events: int  # new balance events (already-known ones are updated, not counted)
    created_at: datetime
    skipped_rows: list[SkippedRow] = field(default_factory=list)

    def __post_init__(self) -> None:
        require_aware(created_at=self.created_at)
