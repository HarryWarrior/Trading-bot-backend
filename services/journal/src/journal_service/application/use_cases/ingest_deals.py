"""Store raw MT5 deals and (re)build the trades of every position they touch."""

from dataclasses import dataclass, field

from journal_service.application.ports.ids import IdGenerator
from journal_service.application.ports.parsing import ParsedBalanceEvent, ParsedTrade
from journal_service.application.ports.repositories import (
    BalanceRepository,
    DealRepository,
    TradeRepository,
)
from journal_service.application.use_cases._build import build_balance_event, build_trade
from journal_service.domain.deal_pairing import (
    PairedBalanceEvent,
    PairedTrade,
    is_trade_deal,
    pair_deals,
)
from journal_service.domain.deals import RawDeal


@dataclass(frozen=True)
class IngestDealsResult:
    received: int
    new: int  # raw deals not stored before
    trades_upserted: int  # closed trades created or rebuilt by this batch
    balance_events: int = 0  # new balance events only
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (position_id, reason)


def _parsed_trade(trade: PairedTrade) -> ParsedTrade:
    return ParsedTrade(
        position_id=trade.position_id,
        symbol=trade.symbol,
        side=trade.side,
        volume=trade.volume,
        open_time=trade.open_time,
        close_time=trade.close_time,
        open_price=trade.open_price,
        close_price=trade.close_price,
        stop_loss=trade.stop_loss,
        take_profit=trade.take_profit,
        commission=trade.commission,
        swap=trade.swap,
        profit=trade.profit,
        comment=trade.comment,
    )


def _parsed_event(event: PairedBalanceEvent) -> ParsedBalanceEvent:
    return ParsedBalanceEvent(
        kind=event.kind,
        amount=event.amount,
        time=event.time,
        source_ref=event.source_ref,
        comment=event.comment,
    )


class IngestDeals:
    def __init__(
        self,
        deals: DealRepository,
        trades: TradeRepository,
        balances: BalanceRepository,
        ids: IdGenerator,
    ) -> None:
        self._deals = deals
        self._trades = trades
        self._balances = balances
        self._ids = ids

    async def execute(
        self, user_id: str, account_ref: str, deals: list[RawDeal]
    ) -> IngestDealsResult:
        new = await self._deals.upsert_many(user_id, account_ref, deals)
        position_ids = sorted({d.position_id for d in deals if is_trade_deal(d)})
        stored = (
            await self._deals.positions_for(user_id, account_ref, position_ids)
            if position_ids
            else []
        )
        # Stored deals already include this batch; balance deals come from the batch only.
        by_ticket = {d.ticket: d for d in stored if is_trade_deal(d)}
        balance_deals = [d for d in deals if not is_trade_deal(d)]
        result = pair_deals([*by_ticket.values(), *balance_deals])

        trades = [
            build_trade(
                _parsed_trade(t),
                user_id=user_id,
                account_ref=account_ref,
                source="mt5",
                import_id=None,
                ids=self._ids,
            )
            for t in result.trades
        ]
        events = [
            build_balance_event(
                _parsed_event(e), user_id=user_id, account_ref=account_ref, ids=self._ids
            )
            for e in result.balance_events
        ]
        created, updated = await self._trades.upsert_many(user_id, trades)
        new_events = await self._balances.upsert_many(user_id, events)
        return IngestDealsResult(
            received=len(deals),
            new=new,
            trades_upserted=created + updated,
            balance_events=new_events,
            skipped=result.skipped,
        )
