"""HTTP schemas. Decimals leave the API as JSON numbers; money is rounded to 2 dp here."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from journal_service.application.ports.repositories import AccountSummary
from journal_service.domain.balance import BalanceEvent, BalanceKind
from journal_service.domain.report_import import ReportImport
from journal_service.domain.trade import Trade

_CENT = Decimal("0.01")
MAX_DEALS_PER_BATCH = 1000


def money(value: Decimal) -> float:
    return float(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def _opt(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


class SkippedRowOut(BaseModel):
    row: int
    reason: str


class ImportOut(BaseModel):
    id: str
    filename: str
    account_ref: str
    trades_created: int
    trades_updated: int
    balance_events: int
    skipped_rows: list[SkippedRowOut]
    created_at: datetime

    @classmethod
    def from_domain(cls, item: ReportImport) -> ImportOut:
        return cls(
            id=item.id,
            filename=item.filename,
            account_ref=item.account_ref,
            trades_created=item.trades_created,
            trades_updated=item.trades_updated,
            balance_events=item.balance_events,
            skipped_rows=[SkippedRowOut(row=s.row, reason=s.reason) for s in item.skipped_rows],
            created_at=item.created_at,
        )


class ImportEnvelope(BaseModel):
    # ``import`` is a Python keyword, so the attribute is aliased to the wire name.
    model_config = ConfigDict(populate_by_name=True)

    import_: ImportOut = Field(alias="import")


class TradeOut(BaseModel):
    id: str
    account_ref: str
    position_id: str | None
    symbol: str
    side: str
    volume: float
    open_time: datetime
    close_time: datetime
    open_price: float
    close_price: float
    stop_loss: float | None
    take_profit: float | None
    commission: float
    swap: float
    profit: float
    net: float
    outcome: str
    duration_minutes: int
    comment: str | None
    source: str
    import_id: str | None

    @classmethod
    def from_domain(cls, trade: Trade) -> TradeOut:
        return cls(
            id=trade.id,
            account_ref=trade.account_ref,
            position_id=trade.position_id,
            symbol=trade.symbol,
            side=trade.side.value,
            volume=float(trade.volume),
            open_time=trade.open_time,
            close_time=trade.close_time,
            open_price=float(trade.open_price),
            close_price=float(trade.close_price),
            stop_loss=_opt(trade.stop_loss),
            take_profit=_opt(trade.take_profit),
            commission=money(trade.commission),
            swap=money(trade.swap),
            profit=money(trade.profit),
            net=money(trade.net),
            outcome=trade.outcome.value,
            duration_minutes=trade.duration_minutes,
            comment=trade.comment,
            source=trade.source,
            import_id=trade.import_id,
        )


class TradeEnvelope(BaseModel):
    trade: TradeOut


class BalanceEventOut(BaseModel):
    id: str
    account_ref: str
    kind: str
    amount: float
    time: datetime
    source_ref: str
    comment: str | None

    @classmethod
    def from_domain(cls, event: BalanceEvent) -> BalanceEventOut:
        return cls(
            id=event.id,
            account_ref=event.account_ref,
            kind=event.kind,
            amount=money(event.amount),
            time=event.time,
            source_ref=event.source_ref,
            comment=event.comment,
        )


class AccountOut(BaseModel):
    account_ref: str
    trades: int
    first_trade_at: datetime
    last_trade_at: datetime

    @classmethod
    def from_domain(cls, account: AccountSummary) -> AccountOut:
        return cls(
            account_ref=account.account_ref,
            trades=account.trades,
            first_trade_at=account.first_trade_at,
            last_trade_at=account.last_trade_at,
        )


class AccountList(BaseModel):
    items: list[AccountOut]


class DatasetOut(BaseModel):
    trades: list[TradeOut]
    balance_events: list[BalanceEventOut]


class IngestTradeIn(BaseModel):
    position_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: Literal["buy", "sell"]
    volume: Decimal
    open_time: AwareDatetime
    close_time: AwareDatetime
    open_price: Decimal
    close_price: Decimal
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    commission: Decimal = Decimal(0)
    swap: Decimal = Decimal(0)
    profit: Decimal
    comment: str | None = None


class IngestBalanceEventIn(BaseModel):
    kind: BalanceKind
    amount: Decimal
    time: AwareDatetime
    source_ref: str = Field(min_length=1)
    comment: str | None = None


class IngestRequest(BaseModel):
    account_ref: str = Field(min_length=1)
    trades: list[IngestTradeIn] = []
    balance_events: list[IngestBalanceEventIn] = []


class IngestOut(BaseModel):
    created: int
    updated: int
    balance_events: int


class IngestDealIn(BaseModel):
    """One raw MT5 deal as sent by the EA bridge; ``time`` is UTC (tz-aware ISO 8601)."""

    ticket: int = Field(ge=0)
    position_id: int = Field(ge=0)
    time: AwareDatetime
    type: int = Field(ge=0)
    entry: int = Field(ge=0)
    symbol: str = ""
    volume: Decimal = Decimal(0)
    price: Decimal = Decimal(0)
    commission: Decimal = Decimal(0)
    swap: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)
    profit: Decimal = Decimal(0)
    sl: Decimal | None = None
    tp: Decimal | None = None
    comment: str | None = None


class IngestDealsRequest(BaseModel):
    user_id: str = Field(min_length=1)
    account_ref: str = Field(min_length=1)
    deals: list[IngestDealIn] = Field(default_factory=list, max_length=MAX_DEALS_PER_BATCH)


class SkippedPositionOut(BaseModel):
    position_id: str
    reason: str


class IngestDealsOut(BaseModel):
    received: int
    new: int
    trades_upserted: int
    balance_events: int
    skipped: list[SkippedPositionOut]
