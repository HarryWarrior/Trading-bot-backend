"""Natural-key helpers for trades that carry no broker position id."""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from journal_service.domain.trade import Side


def _decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def row_hash(
    account_ref: str,
    symbol: str,
    side: Side,
    open_time: datetime,
    close_time: datetime,
    volume: Decimal,
    open_price: Decimal,
    close_price: Decimal,
    profit: Decimal,
) -> str:
    canonical = "|".join(
        [
            account_ref,
            symbol,
            str(side.value),
            _time(open_time),
            _time(close_time),
            _decimal(volume),
            _decimal(open_price),
            _decimal(close_price),
            _decimal(profit),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
