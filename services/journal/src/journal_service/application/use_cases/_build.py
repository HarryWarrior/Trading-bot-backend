"""Shared conversion from parsed rows to stored entities."""

from typing import Literal

from journal_service.application.ports.ids import IdGenerator
from journal_service.application.ports.parsing import ParsedBalanceEvent, ParsedTrade
from journal_service.domain.balance import BalanceEvent
from journal_service.domain.keys import row_hash
from journal_service.domain.trade import Trade


def build_trade(
    parsed: ParsedTrade,
    *,
    user_id: str,
    account_ref: str,
    source: Literal["report", "mt5"],
    import_id: str | None,
    ids: IdGenerator,
) -> Trade:
    digest = None
    if parsed.position_id is None:
        digest = row_hash(
            account_ref,
            parsed.symbol,
            parsed.side,
            parsed.open_time,
            parsed.close_time,
            parsed.volume,
            parsed.open_price,
            parsed.close_price,
            parsed.profit,
        )
    return Trade(
        id=ids.new_id(),
        user_id=user_id,
        account_ref=account_ref,
        position_id=parsed.position_id,
        row_hash=digest,
        source=source,
        import_id=import_id,
        symbol=parsed.symbol,
        side=parsed.side,
        volume=parsed.volume,
        open_time=parsed.open_time,
        close_time=parsed.close_time,
        open_price=parsed.open_price,
        close_price=parsed.close_price,
        stop_loss=parsed.stop_loss,
        take_profit=parsed.take_profit,
        commission=parsed.commission,
        swap=parsed.swap,
        profit=parsed.profit,
        comment=parsed.comment,
    )


def build_balance_event(
    parsed: ParsedBalanceEvent, *, user_id: str, account_ref: str, ids: IdGenerator
) -> BalanceEvent:
    return BalanceEvent(
        id=ids.new_id(),
        user_id=user_id,
        account_ref=account_ref,
        kind=parsed.kind,
        amount=parsed.amount,
        time=parsed.time,
        source_ref=parsed.source_ref,
        comment=parsed.comment,
    )
