"""Pairs raw MT5 deals into closed trades and balance events.

Ported from ``mt5_service.domain.trades`` (same rules, journal types, no server-time conversion
because the bridge already sends UTC):

- trade deals (BUY/SELL) are grouped by ``position_id``; side = side of the IN deal; volume = sum
  of IN volumes; a position is closed only when the exit volume equals the entry volume (Decimal
  equality). Open positions are counted, never returned.
- positions containing an INOUT (reversal) deal, an unknown entry value, a deal with volume <= 0,
  entry deals of both sides, no entry deal or more exit than entry volume are reported in
  ``skipped`` with a reason (never raised, so one bad stored deal cannot block later batches).
- BUY_CANCELED / SELL_CANCELED deals are ignored. BALANCE -> deposit/withdrawal, CREDIT -> credit,
  any other type (known or not) -> signed ``adjustment``; zero amounts are dropped.
- ``fee`` is folded into ``commission`` because the journal has no fee field.
- stop loss / take profit come from the first entry deal.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from journal_service.domain.balance import BalanceKind
from journal_service.domain.deals import DealEntry, DealType, RawDeal
from journal_service.domain.trade import Side

_PRICE_PLACES = 10
_EXIT_ENTRIES = (DealEntry.OUT, DealEntry.OUT_BY)
_TRADE_TYPES = (DealType.BUY, DealType.SELL)
_IGNORED_TYPES = (DealType.BUY_CANCELED, DealType.SELL_CANCELED)
_KNOWN_ENTRIES = frozenset(int(e) for e in DealEntry)


@dataclass(frozen=True)
class PairedTrade:
    position_id: str
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
class PairedBalanceEvent:
    kind: BalanceKind
    amount: Decimal  # signed
    time: datetime
    source_ref: str  # the deal ticket
    comment: str | None


@dataclass(frozen=True)
class PairingResult:
    trades: list[PairedTrade] = field(default_factory=list)
    balance_events: list[PairedBalanceEvent] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (position_id, reason)
    open_positions: int = 0


def is_trade_deal(deal: RawDeal) -> bool:
    return deal.type in _TRADE_TYPES


def _balance_event(deal: RawDeal) -> PairedBalanceEvent | None:
    comment = deal.comment or None
    kind: BalanceKind
    if deal.type == DealType.BALANCE:
        if deal.profit == 0:
            return None
        kind = "deposit" if deal.profit > 0 else "withdrawal"
        amount = deal.profit
    elif deal.type == DealType.CREDIT:
        kind, amount = "credit", deal.profit
    else:
        kind = "adjustment"
        amount = deal.profit + deal.commission + deal.swap + deal.fee
        if amount == 0:
            return None
    return PairedBalanceEvent(kind, amount, deal.time, str(deal.ticket), comment)


def _weighted_price(deals: list[RawDeal]) -> Decimal:
    total = sum((d.volume for d in deals), Decimal(0))
    price = sum((d.price * d.volume for d in deals), Decimal(0)) / total
    exponent = price.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -_PRICE_PLACES:
        price = price.quantize(Decimal(1).scaleb(-_PRICE_PLACES))
    return price


def _pair_position(position_id: int, deals: list[RawDeal]) -> PairedTrade | str | None:
    """Return a trade, a skip reason (str) or None when the position is still open."""
    for d in deals:
        if d.entry not in _KNOWN_ENTRIES:
            return f"unknown deal entry {int(d.entry)}"
    if any(d.volume <= 0 for d in deals):
        return "non-positive deal volume"
    if any(d.entry == DealEntry.INOUT for d in deals):
        return "reversal (INOUT) deals are not supported yet"
    entries = [d for d in deals if d.entry == DealEntry.IN]
    exits = [d for d in deals if d.entry in _EXIT_ENTRIES]
    if not entries:
        return "no entry deal in the history"
    if len({d.type for d in entries}) > 1:
        return "mixed entry sides"
    entry_volume = sum((d.volume for d in entries), Decimal(0))
    exit_volume = sum((d.volume for d in exits), Decimal(0))
    if exit_volume > entry_volume:
        return "exit volume exceeds entry volume"
    if exit_volume < entry_volume:
        return None
    first = entries[0]
    return PairedTrade(
        position_id=str(position_id),
        symbol=first.symbol,
        side=Side.BUY if first.type == DealType.BUY else Side.SELL,
        volume=entry_volume,
        open_time=first.time,
        close_time=exits[-1].time,
        open_price=_weighted_price(entries),
        close_price=_weighted_price(exits),
        stop_loss=first.sl,
        take_profit=first.tp,
        commission=sum((d.commission + d.fee for d in deals), Decimal(0)),
        swap=sum((d.swap for d in deals), Decimal(0)),
        profit=sum((d.profit for d in deals), Decimal(0)),
        comment=first.comment or None,
    )


def pair_deals(deals: list[RawDeal]) -> PairingResult:
    ordered = sorted(deals, key=lambda d: (d.time, d.ticket))
    positions: dict[int, list[RawDeal]] = {}
    balance_events: list[PairedBalanceEvent] = []
    for deal in ordered:
        if deal.type in _IGNORED_TYPES:
            continue
        if is_trade_deal(deal):
            positions.setdefault(deal.position_id, []).append(deal)
        else:
            event = _balance_event(deal)
            if event is not None:
                balance_events.append(event)

    trades: list[PairedTrade] = []
    skipped: list[tuple[str, str]] = []
    open_positions = 0
    for position_id, group in positions.items():
        paired = _pair_position(position_id, group)
        if paired is None:
            open_positions += 1
        elif isinstance(paired, str):
            skipped.append((str(position_id), paired))
        else:
            trades.append(paired)
    trades.sort(key=lambda t: (t.close_time, t.position_id))
    return PairingResult(trades, balance_events, skipped, open_positions)
