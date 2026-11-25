"""Response models. Decimals leave as JSON numbers (money 2 dp, prices unrounded); unknown = null."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from mt5_service.application.use_cases.get_status import AccountStatus
from mt5_service.domain.account import LinkedAccount, SyncResult
from mt5_service.domain.deals import Candle


def money(value: Decimal | None) -> float | None:
    return None if value is None else float(round(value, 2))


class SyncResultOut(BaseModel):
    created: int
    updated: int
    balance_events: int
    open_positions: int
    skipped_positions: int

    @classmethod
    def from_domain(cls, result: SyncResult) -> SyncResultOut:
        return cls(
            created=result.created,
            updated=result.updated,
            balance_events=result.balance_events,
            open_positions=result.open_positions,
            skipped_positions=result.skipped_positions,
        )


class AccountOut(BaseModel):
    id: str
    account_ref: str
    login: int
    server: str
    name: str
    currency: str
    trade_mode: str
    company: str
    linked_at: datetime
    last_sync_at: datetime | None
    last_sync_result: SyncResultOut | None

    @classmethod
    def from_domain(cls, account: LinkedAccount) -> AccountOut:
        result = account.last_sync_result
        return cls(
            id=account.id,
            account_ref=account.account_ref,
            login=account.login,
            server=account.server,
            name=account.name,
            currency=account.currency,
            trade_mode=account.trade_mode,
            company=account.company,
            linked_at=account.linked_at,
            last_sync_at=account.last_sync_at,
            last_sync_result=None if result is None else SyncResultOut.from_domain(result),
        )


class AccountEnvelope(BaseModel):
    account: AccountOut


class AccountsEnvelope(BaseModel):
    accounts: list[AccountOut]


class StatusOut(BaseModel):
    connected: bool
    balance: float | None
    equity: float | None
    as_of: datetime | None
    last_sync_at: datetime | None

    @classmethod
    def from_domain(cls, status: AccountStatus) -> StatusOut:
        return cls(
            connected=status.connected,
            balance=money(status.balance),
            equity=money(status.equity),
            as_of=status.as_of,
            last_sync_at=status.last_sync_at,
        )


class StatusEnvelope(BaseModel):
    status: StatusOut


class ResultEnvelope(BaseModel):
    result: SyncResultOut


class CandleOut(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int

    @classmethod
    def from_domain(cls, candle: Candle) -> CandleOut:
        return cls(
            time=candle.time,
            open=float(candle.open),
            high=float(candle.high),
            low=float(candle.low),
            close=float(candle.close),
            tick_volume=candle.tick_volume,
        )


class RatesOut(BaseModel):
    symbol: str
    timeframe: str
    candles: list[CandleOut]


class UnlinkedOut(BaseModel):
    unlinked: bool = True
