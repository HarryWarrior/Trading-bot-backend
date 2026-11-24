"""Builds closed trades and balance events from MT5 deals.

Rules (see README): grouped by ``position_id``; side = side of the IN deal; volume = sum of IN
volumes; a position is closed only when the exit volume equals the entry volume (Decimal
equality). Open positions are counted, never sent. Positions containing an INOUT (reversal) deal
are not supported yet: they are reported in ``skipped_positions`` with a reason instead of being
guessed. BUY_CANCELED / SELL_CANCELED deals are ignored (neither balance nor trades).
``fee`` is folded into ``commission`` because journal has no fee field.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from mt5_service.domain.deals import Deal, DealEntry, DealType
from mt5_service.domain.time import to_utc

BalanceKind = Literal["deposit", "withdrawal", "credit", "adjustment"]

_EXIT_ENTRIES = (DealEntry.OUT, DealEntry.OUT_BY)
_TRADE_TYPES = (DealType.BUY, DealType.SELL)
_IGNORED_TYPES = (DealType.BUY_CANCELED, DealType.SELL_CANCELED)


@dataclass(frozen=True)
class TradeOut:
    """Matches journal's ``IngestTradeIn``."""

    position_id: str
    symbol: str
    side: Literal["buy", "sell"]
    volume: Decimal
    open_time: datetime
    close_time: datetime
    open_price: Decimal
    close_price: Decimal
    commission: Decimal
    swap: Decimal
    profit: Decimal
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    comment: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "side": self.side,
            "volume": str(self.volume),
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat(),
            "open_price": str(self.open_price),
            "close_price": str(self.close_price),
            "stop_loss": None if self.stop_loss is None else str(self.stop_loss),
            "take_profit": None if self.take_profit is None else str(self.take_profit),
            "commission": str(self.commission),
            "swap": str(self.swap),
            "profit": str(self.profit),
            "comment": self.comment,
        }


@dataclass(frozen=True)
class BalanceEventOut:
    """Matches journal's ``IngestBalanceEventIn``."""

    kind: BalanceKind
    amount: Decimal  # signed
    time: datetime
    source_ref: str
    comment: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "amount": str(self.amount),
            "time": self.time.isoformat(),
            "source_ref": self.source_ref,
            "comment": self.comment,
        }


@dataclass(frozen=True)
class BuildResult:
    trades: list[TradeOut] = field(default_factory=list)
    balance_events: list[BalanceEventOut] = field(default_factory=list)
    open_positions: int = 0
    skipped_positions: list[tuple[str, str]] = field(default_factory=list)  # (position_id, reason)


def _balance_event(deal: Deal, offset: timedelta) -> BalanceEventOut | None:
    time = to_utc(deal.time_server, offset)
    comment = deal.comment or None
    if deal.type is DealType.BALANCE:
        if deal.profit == 0:
            return None
        kind: BalanceKind = "deposit" if deal.profit > 0 else "withdrawal"
        amount = deal.profit
    elif deal.type is DealType.CREDIT:
        kind, amount = "credit", deal.profit
    else:
        kind = "adjustment"
        amount = deal.profit + deal.commission + deal.swap + deal.fee
    return BalanceEventOut(kind, amount, time, str(deal.ticket), comment)


def _weighted_price(deals: list[Deal]) -> Decimal:
    total = sum((d.volume for d in deals), Decimal(0))
    return sum((d.price * d.volume for d in deals), Decimal(0)) / total


def _build_position(
    position_id: int, deals: list[Deal], offset: timedelta
) -> TradeOut | str | None:
    """Returns a trade, a skip reason (str) or None when the position is still open."""
    if any(d.entry is DealEntry.INOUT for d in deals):
        return "reversal (INOUT) deals are not supported yet"
    entries = [d for d in deals if d.entry is DealEntry.IN]
    exits = [d for d in deals if d.entry in _EXIT_ENTRIES]
    if not entries:
        return "no entry deal in the history"
    entry_volume = sum((d.volume for d in entries), Decimal(0))
    exit_volume = sum((d.volume for d in exits), Decimal(0))
    if exit_volume > entry_volume:
        return "exit volume exceeds entry volume"
    if exit_volume < entry_volume:
        return None
    first = entries[0]
    return TradeOut(
        position_id=str(position_id),
        symbol=first.symbol,
        side="buy" if first.type is DealType.BUY else "sell",
        volume=entry_volume,
        open_time=to_utc(first.time_server, offset),
        close_time=to_utc(exits[-1].time_server, offset),
        open_price=_weighted_price(entries),
        close_price=_weighted_price(exits),
        commission=sum((d.commission + d.fee for d in deals), Decimal(0)),
        swap=sum((d.swap for d in deals), Decimal(0)),
        profit=sum((d.profit for d in deals), Decimal(0)),
        comment=first.comment or None,
    )


def build_trades(deals: list[Deal], offset: timedelta) -> BuildResult:
    ordered = sorted(deals, key=lambda d: (d.time_server, d.ticket))
    positions: dict[int, list[Deal]] = {}
    balance_events: list[BalanceEventOut] = []
    for deal in ordered:
        if deal.type in _IGNORED_TYPES:
            continue
        if deal.type in _TRADE_TYPES:
            positions.setdefault(deal.position_id, []).append(deal)
        else:
            event = _balance_event(deal, offset)
            if event is not None:
                balance_events.append(event)

    trades: list[TradeOut] = []
    skipped: list[tuple[str, str]] = []
    open_positions = 0
    for position_id, group in positions.items():
        built = _build_position(position_id, group, offset)
        if built is None:
            open_positions += 1
        elif isinstance(built, str):
            skipped.append((str(position_id), built))
        else:
            trades.append(built)
    trades.sort(key=lambda t: (t.close_time, t.position_id))
    return BuildResult(trades, balance_events, open_positions, skipped)
