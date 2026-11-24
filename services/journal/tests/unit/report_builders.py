"""Builds synthetic MT5 reports in memory. No real data lives in the repository."""

from __future__ import annotations

import io
import warnings
from collections.abc import Sequence

import openpyxl

POSITION_HEADER = [
    "Time", "Position", "Symbol", "Type", "Volume", "Price", "S / L", "T / P",
    "Time", "Price", "Commission", "Swap", "Profit",
]  # fmt: skip
DEAL_HEADER = [
    "Time", "Deal", "Symbol", "Type", "Direction", "Volume", "Price", "Order",
    "Commission", "Fee", "Swap", "Profit", "Balance", "Comment",
]  # fmt: skip

# open_time, position, symbol, type, volume, open_price, sl, tp, close_time, close_price,
# commission, swap, profit
DEFAULT_POSITIONS: list[Sequence] = [
    ["2026.01.22 15:55:08", "1001", "XAUUSD", "sell", "0.06", "4 800.50", "4 810.00", "0.00",
     "2026.01.22 16:32:00", "4 790.50", "-1.20", "0.00", "60.00"],
    ["2026.01.23 09:00:00", "1002", "EURUSD", "buy", "0.10", "1.10000", "1.09000", "1.12000",
     "2026.01.23 10:30:00", "1.10500", "-0.70", "-0.10", "50.00"],
    ["2026.01.24 11:00:00", "1003", "EURUSD", "buy", "0.10", "1.10500", "0.00", "0.00",
     "2026.01.24 12:00:00", "1.10200", "-0.70", "0.00", "- 30.00"],
]  # fmt: skip


def balance_deal(time: str, ticket: str, amount: str, balance: str, kind="balance", comment=""):
    return [time, ticket, "", kind, "", "", "", "", "", "", "", amount, balance, comment]


def money_deal(
    time: str,
    ticket: str,
    kind: str,
    profit="",
    commission="",
    fee="",
    swap="",
    comment="",
):
    """A non-trade Deals row whose amount may sit in any of the money columns."""
    return [time, ticket, "", kind, "", "", "", "", commission, fee, swap, profit, "", comment]


DEFAULT_DEALS: list[Sequence] = [
    balance_deal("2026.01.20 08:00:00", "1", "10 000.00", "10 000.00", comment="Initial deposit"),
    balance_deal("2026.01.25 08:00:00", "2", "-500.00", "9 500.00", comment="Withdrawal"),
    ["2026.01.22 15:55:08", "3", "XAUUSD", "sell", "in", "0.06", "4 800.50", "9", "0", "0",
     "0", "0.00", "10 000.00", ""],
]  # fmt: skip


def _new_workbook() -> openpyxl.Workbook:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # openpyxl 3.1 uses datetime.utcnow
        return openpyxl.Workbook()


def _put(ws, row: int, values: Sequence) -> int:
    for col, value in enumerate(values, start=1):
        if value not in ("", None):
            ws.cell(row=row, column=col, value=value)
    return row + 1


def build_mt5_xlsx(
    positions: Sequence[Sequence] | None = None,
    deals: Sequence[Sequence] | None = None,
    account: str | None = "12345678 (USD, Demo-Server, demo, Hedge)",
    spanish: bool = False,
) -> bytes:
    wb = _new_workbook()
    ws = wb.active
    row = _put(ws, 1, ["Trade History Report"])
    row = _put(ws, row, ["Name:", None, None, "Synthetic Trader"])
    if account is not None:
        row = _put(ws, row, ["Account:", None, None, account])
    row = _put(ws, row, ["Company:", None, None, "Synthetic Broker"])
    row = _put(ws, row, ["Date:", None, None, "2026.02.01 10:00"])
    row = _put(ws, row, ["Positions"])
    header = POSITION_HEADER
    if spanish:
        header = [
            "Hora", "Posición", "Símbolo", "Tipo", "Volumen", "Precio", "S / L", "T / P",
            "Hora", "Precio", "Comisión", "Swap", "Beneficio",
        ]  # fmt: skip
    row = _put(ws, row, header)
    for position in DEFAULT_POSITIONS if positions is None else positions:
        row = _put(ws, row, position)
    row = _put(
        ws,
        row,
        [None, None, None, None, None, None, None, None, None, None, "-2.60", "-0.10", "80.00"],
    )
    row += 1
    row = _put(ws, row, ["Orders"])
    row = _put(
        ws, row, ["Open Time", "Order", "Symbol", "Type", "Volume", "Price", "S / L", "T / P"]
    )
    row = _put(ws, row, ["2026.01.22 15:55:08", "9001", "XAUUSD", "sell", "0.06", "4 800.50"])
    row = _put(ws, row, ["2026.01.22 15:55:09", "9002", "XAUUSD", "sell limit", "0.06", "4 900.00"])
    row += 1
    row = _put(ws, row, ["Deals"])
    row = _put(ws, row, DEAL_HEADER)
    for deal in DEFAULT_DEALS if deals is None else deals:
        row = _put(ws, row, deal)
    # Deals totals line: Time/Deal/Symbol/Type empty, sums in Commission/Fee/Swap/Profit/Balance.
    row = _put(ws, row, [None] * 8 + ["-2.60", "0.00", "-0.10", "9 500.00", "9 500.00"])
    row += 1
    # Account summary block: label in column A, value in the column that maps to Type.
    for label, value, label2, value2 in (
        ("Balance:", "9 128.38", "Free Margin:", "9 128.38"),
        ("Credit Facility:", "0.00", "Margin:", "0.00"),
        ("Floating P/L:", "0.00", "Margin Level:", ""),
        ("Equity:", "9 128.38", None, None),
    ):
        row = _put(ws, row, [label, None, None, value, None, None, label2, value2])
    row += 1
    row = _put(ws, row, ["Results"])
    row = _put(ws, row, ["Total Net Profit:", None, None, "999 999.00"])
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # openpyxl 3.1 uses datetime.utcnow on save
        wb.save(buffer)
    return buffer.getvalue()


def build_flat_xlsx(rows: Sequence[Sequence], header: Sequence[str], title: bool = True) -> bytes:
    """Header on sheet row 3. Without the title, rows 1-2 are empty (never written)."""
    wb = _new_workbook()
    ws = wb.active
    if title:
        _put(ws, 1, ["Some title row"])
    row = _put(ws, 3, header)
    for values in rows:
        row = _put(ws, row, values)
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # openpyxl 3.1 uses datetime.utcnow on save
        wb.save(buffer)
    return buffer.getvalue()


def csv_bytes(text: str, encoding: str = "utf-8") -> bytes:
    return text.encode(encoding)
