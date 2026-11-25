"""Request/response models of the bridge API (HTTP edge only)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from mt5_bridge_service.application.ports.journal import IngestDealsResult
from mt5_bridge_service.application.use_cases.list_accounts import AccountOverview
from mt5_bridge_service.domain.account import BrokerAccount, Heartbeat
from mt5_bridge_service.domain.deal import MAX_DEALS_PER_REQUEST, RawDeal
from mt5_bridge_service.domain.token import MAX_NAME_LENGTH, IngestToken

_CENT = Decimal("0.01")
# MT5 DEAL_TYPE_BUY / DEAL_TYPE_SELL: the only deal types that move a position.
_TRADE_DEAL_TYPES = (0, 1)


def money(value: Decimal) -> float:
    return float(value.quantize(_CENT, rounding=ROUND_HALF_UP))


# --- EA-facing ------------------------------------------------------------------------------


class DealIn(BaseModel):
    """One raw MT5 deal; ``time`` must carry its offset (the EA sends UTC with ``Z``)."""

    ticket: int = Field(ge=0)
    position_id: int = Field(ge=0)
    time: AwareDatetime
    type: int = Field(ge=0)
    entry: int = Field(ge=0)
    symbol: str = Field(default="", max_length=64)
    volume: Decimal = Decimal(0)
    price: Decimal = Decimal(0)
    commission: Decimal = Decimal(0)
    swap: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)
    profit: Decimal = Decimal(0)
    sl: Decimal | None = None
    tp: Decimal | None = None
    comment: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _trade_deals_need_volume(self) -> DealIn:
        # Same rule as journal: rejected here so the EA gets a 422 instead of a forwarded batch.
        if self.type in _TRADE_DEAL_TYPES and self.volume <= 0:
            raise ValueError("BUY/SELL deals need a volume greater than 0")
        return self

    def to_domain(self) -> RawDeal:
        return RawDeal(
            ticket=self.ticket,
            position_id=self.position_id,
            time=self.time.astimezone(UTC),
            type=self.type,
            entry=self.entry,
            symbol=self.symbol,
            volume=self.volume,
            price=self.price,
            commission=self.commission,
            swap=self.swap,
            profit=self.profit,
            sl=self.sl,
            tp=self.tp,
            comment=self.comment,
            fee=self.fee,
        )


class IngestDealsIn(BaseModel):
    account_login: int = Field(gt=0)
    server: str = Field(min_length=1, max_length=128)
    deals: list[DealIn] = Field(default_factory=list, max_length=MAX_DEALS_PER_REQUEST)


class SkippedPositionOut(BaseModel):
    position_id: str
    reason: str


class IngestDealsOut(BaseModel):
    received: int
    new: int
    trades_upserted: int
    balance_events: int = 0
    skipped: list[SkippedPositionOut] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, result: IngestDealsResult) -> IngestDealsOut:
        return cls(
            received=result.received,
            new=result.new,
            trades_upserted=result.trades_upserted,
            balance_events=result.balance_events,
            skipped=[
                SkippedPositionOut(position_id=s.position_id, reason=s.reason)
                for s in result.skipped
            ],
        )


class HeartbeatIn(BaseModel):
    account_login: int = Field(gt=0)
    server: str = Field(min_length=1, max_length=128)
    balance: Decimal
    equity: Decimal
    terminal_build: int | None = Field(default=None, ge=0)

    def to_domain(self) -> Heartbeat:
        return Heartbeat(
            login=self.account_login,
            server=self.server,
            balance=self.balance,
            equity=self.equity,
            terminal_build=self.terminal_build,
        )


# --- user-facing ----------------------------------------------------------------------------


class CreateTokenIn(BaseModel):
    name: str = Field(max_length=MAX_NAME_LENGTH * 2)


class TokenOut(BaseModel):
    """A token as listed: never the hash, never the plaintext."""

    id: str
    name: str
    scope: str
    active: bool
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    @classmethod
    def from_domain(cls, token: IngestToken) -> TokenOut:
        return cls(
            id=token.id,
            name=token.name,
            scope=token.scope,
            active=token.is_active,
            created_at=token.created_at,
            last_used_at=token.last_used_at,
            revoked_at=token.revoked_at,
        )


class CreatedTokenOut(BaseModel):
    """The only response that ever contains the plaintext token."""

    token: TokenOut
    plaintext_token: str


class TokenEnvelope(BaseModel):
    token: TokenOut


class AccountOut(BaseModel):
    account_ref: str
    login: int
    server: str
    balance: float
    equity: float
    terminal_build: int | None
    last_heartbeat: datetime | None
    last_deal_at: datetime | None
    status: str

    @classmethod
    def from_domain(cls, account: BrokerAccount, status: str) -> AccountOut:
        return cls(
            account_ref=account.account_ref,
            login=account.login,
            server=account.server,
            balance=money(account.balance),
            equity=money(account.equity),
            terminal_build=account.terminal_build,
            last_heartbeat=account.last_heartbeat,
            last_deal_at=account.last_deal_at,
            status=status,
        )

    @classmethod
    def from_overview(cls, overview: AccountOverview) -> AccountOut:
        return cls.from_domain(overview.account, overview.status.value)


class AccountEnvelope(BaseModel):
    account: AccountOut
