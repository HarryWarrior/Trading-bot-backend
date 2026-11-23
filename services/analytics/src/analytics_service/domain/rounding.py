"""Single rounding rule for every KPI that leaves the domain."""

from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


def round_money(value: Decimal) -> Decimal:
    """Money, ratios and percentages: 2 decimals, half up."""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)
