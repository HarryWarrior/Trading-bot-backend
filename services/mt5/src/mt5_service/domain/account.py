from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

TradeMode = Literal["demo", "real", "contest"]


def account_ref(login: int, server: str) -> str:
    """Identity of a terminal account, identical to what MT5 reports (dedupes with imports)."""
    return f"{login}@{server}"


@dataclass(frozen=True)
class TerminalAccount:
    """What the running terminal reports. There is deliberately no password/secret field."""

    login: int
    server: str
    name: str
    currency: str
    balance: Decimal
    equity: Decimal
    trade_mode: TradeMode
    company: str

    @property
    def account_ref(self) -> str:
        return account_ref(self.login, self.server)


@dataclass(frozen=True)
class SyncResult:
    created: int
    updated: int
    balance_events: int
    open_positions: int
    skipped_positions: int


@dataclass(frozen=True)
class LinkedAccount:
    id: str
    user_id: str
    account_ref: str
    login: int
    server: str
    name: str
    currency: str
    trade_mode: TradeMode
    company: str
    linked_at: datetime
    last_sync_at: datetime | None = None
    last_sync_result: SyncResult | None = None
