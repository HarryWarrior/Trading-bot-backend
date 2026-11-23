"""Shared fixtures: the sample dataset is read from data/samples (test data only)."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest
from builders import utc

from analytics_service.domain.dataset import Dataset, TradeRecord

SAMPLE_CSV = Path(__file__).resolve().parents[3] / "data" / "samples" / "sample_trades.csv"


@pytest.fixture
def sample_dataset() -> Dataset:
    with SAMPLE_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    trades = [
        TradeRecord(
            symbol=row["Symbol"],
            side=row["Type"],
            open_time=utc(row["Open Time"]),
            close_time=utc(row["Close Time"]),
            net=Decimal(row["Profit"]),
        )
        for row in rows
    ]
    return Dataset(trades=trades, balance_events=[])
