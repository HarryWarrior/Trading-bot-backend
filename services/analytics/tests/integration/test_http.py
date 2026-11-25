"""HTTP tests for analytics with a fake TradeSource (no journal, no database)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from builders import make_balance, make_trade
from fastapi.testclient import TestClient
from pydantic import ValidationError

from analytics_service.application.ports.trade_source import (
    SourceUnauthenticated,
    SourceUnavailable,
)
from analytics_service.domain.dataset import Dataset
from analytics_service.main import create_app
from analytics_service.settings import AnalyticsSettings

SECRET = "test-secret-key-with-enough-length-0123456789"
BASE = "/api/v1/analytics"


def token_for(user_id: str = "alice", secret: str = SECRET) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "email": f"{user_id}@mail.com",
        "role": "user",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


class FakeSource:
    def __init__(self, dataset: Dataset | None = None, error: Exception | None = None) -> None:
        self.dataset = dataset or Dataset()
        self.error = error
        self.calls: list[tuple[str, str | None]] = []

    async def fetch(self, token: str, account_ref: str | None) -> Dataset:
        self.calls.append((token, account_ref))
        if self.error:
            raise self.error
        return self.dataset


def make_client(source: FakeSource) -> TestClient:
    settings = AnalyticsSettings(
        _env_file=None, environment="test", jwt_secret_key=SECRET, journal_url="http://journal.test"
    )
    return TestClient(create_app(settings, trade_source=source))


@pytest.fixture
def dataset() -> Dataset:
    return Dataset(
        trades=[
            make_trade("2026-01-05 10:00:00", "100.005", symbol="EURUSD"),
            make_trade("2026-01-05 11:00:00", "-40", symbol="GBPUSD"),
            make_trade("2026-02-06 12:00:00", "60", symbol="EURUSD"),
        ],
        balance_events=[make_balance("2026-01-01 00:00:00", "1000")],
    )


def headers(token: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token or token_for()}"}


def test_summary_values_and_shape(dataset):
    client = make_client(FakeSource(dataset))
    response = client.get(f"{BASE}/summary", headers=headers())
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    summary = body["data"]["summary"]
    assert summary["total_trades"] == 3
    assert summary["net_profit"] == 120.01
    assert summary["win_rate"] == 66.67
    assert summary["starting_balance"] == 1000.0
    assert summary["best_day"] == "2026-01-05"
    assert summary["worst_day"] == "2026-02-06"
    assert summary["profit_factor"] == 4.0


def test_summary_unknowns_are_null_and_empty_user_is_200():
    client = make_client(FakeSource(Dataset()))
    response = client.get(f"{BASE}/summary", headers=headers())
    assert response.status_code == 200
    summary = response.json()["data"]["summary"]
    assert summary["total_trades"] == 0
    assert summary["net_profit"] == 0
    assert summary["max_drawdown_pct"] is None
    assert summary["starting_balance"] is None
    assert summary["best_day"] is None


def test_account_ref_and_exact_token_are_forwarded(dataset):
    source = FakeSource(dataset)
    token = token_for()
    make_client(source).get(
        f"{BASE}/summary", params={"account_ref": "123@Live"}, headers=headers(token)
    )
    assert source.calls == [(token, "123@Live")]


def test_account_ref_defaults_to_none(dataset):
    source = FakeSource(dataset)
    make_client(source).get(f"{BASE}/daily", headers=headers())
    assert source.calls[0][1] is None


def test_equity_starts_at_starting_balance_at_first_balance_event(dataset):
    client = make_client(FakeSource(dataset))
    points = client.get(f"{BASE}/equity", headers=headers()).json()["data"]["points"]
    assert points[0] == {"time": "2026-01-01T00:00:00Z", "equity": 1000.0}
    assert [p["equity"] for p in points] == [1000.0, 1100.01, 1060.01, 1120.01]


def test_equity_without_balance_has_no_synthetic_first_point():
    client = make_client(FakeSource(Dataset(trades=[make_trade("2026-01-05 10:00:00", "10")])))
    points = client.get(f"{BASE}/equity", headers=headers()).json()["data"]["points"]
    assert [p["equity"] for p in points] == [10.0]


def test_daily_monthly_symbol_hourly(dataset):
    client = make_client(FakeSource(dataset))
    daily = client.get(f"{BASE}/daily", headers=headers()).json()["data"]["days"]
    assert daily[0] == {"day": "2026-01-05", "trades": 2, "net": 60.01}
    monthly = client.get(f"{BASE}/monthly", headers=headers()).json()["data"]["months"]
    assert monthly == [
        {"month": "2026-01", "trades": 2, "net": 60.01},
        {"month": "2026-02", "trades": 1, "net": 60.0},
    ]
    symbols = client.get(f"{BASE}/by-symbol", headers=headers()).json()["data"]["symbols"]
    assert symbols[0] == {
        "symbol": "EURUSD",
        "trades": 2,
        "wins": 2,
        "win_rate": 100.0,
        "net": 160.01,
    }
    hours = client.get(f"{BASE}/hourly", headers=headers()).json()["data"]["hours"]
    assert {h["hour"] for h in hours} == {10, 11, 12}


def test_journal_unreachable_is_503():
    client = make_client(FakeSource(error=SourceUnavailable("down")))
    response = client.get(f"{BASE}/summary", headers=headers())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "JOURNAL_UNAVAILABLE"


def test_journal_rejecting_token_is_401():
    client = make_client(FakeSource(error=SourceUnauthenticated()))
    response = client.get(f"{BASE}/summary", headers=headers())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("path", ["summary", "equity", "daily", "monthly", "by-symbol", "hourly"])
def test_requires_token(path):
    source = FakeSource()
    response = make_client(source).get(f"{BASE}/{path}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert source.calls == []


def test_bad_token_never_reaches_journal():
    source = FakeSource()
    response = make_client(source).get(
        f"{BASE}/summary", headers=headers(token_for(secret="x" * 40))
    )
    assert response.status_code == 401
    assert source.calls == []


def test_health_needs_no_token():
    assert make_client(FakeSource()).get("/health").status_code == 200


def test_settings_require_long_secret():
    with pytest.raises(ValidationError):
        AnalyticsSettings(_env_file=None, jwt_secret_key="short")
