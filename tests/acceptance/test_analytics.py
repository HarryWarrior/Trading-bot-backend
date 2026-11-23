"""Acceptance: analytics over the sample report (`data/raw/sample_trades.csv`).

Expected values were computed by hand from the 10 sample trades:
gross profit 1750, gross loss 300, equity 200→250→100→…→1450 (peak 250, trough 100).
"""

from pathlib import Path

import pytest

from tests.acceptance.conftest import known_bug

API = "/api/v1/analytics"
SAMPLE = Path(__file__).resolve().parents[2] / "data" / "raw" / "sample_trades.csv"


@pytest.fixture()
def uploaded_report(client, workdir):
    """Upload a report under another name, then remove it so later tests see the sample again."""

    def _upload(name: str, content: bytes):
        response = client.post(f"{API}/upload-trades", files={"file": (name, content, "text/csv")})
        created.append(workdir / "data" / "raw" / name)
        return response

    created: list[Path] = []
    yield _upload
    for path in created:
        path.unlink(missing_ok=True)


def test_summary_kpis_match_sample(client):
    summary = client.get(f"{API}/summary").json()
    assert summary["total_trades"] == 10
    assert summary["winning_trades"] == 7
    assert summary["losing_trades"] == 3
    assert summary["total_profit"] == 1450.0
    assert summary["win_rate"] == 70.0
    assert summary["payoff_ratio"] == 2.5
    assert summary["max_drawdown"] == -150.0
    assert summary["longest_win_streak"] == 3
    assert summary["best_day"] == "2025-01-16"


@pytest.mark.parametrize(
    "path",
    [
        "/trades",
        "/filter",
        "/timeseries",
        "/by-symbol",
        "/hourly-heatmap",
        "/daily-stats",
        "/monthly-stats",
    ],
)
def test_analytics_endpoints_respond(client, path):
    assert client.get(API + path).status_code == 200


def test_trades_endpoint_paginates(client):
    assert len(client.get(f"{API}/trades", params={"limit": 3}).json()) == 3


def test_filter_by_symbol(client):
    body = client.get(f"{API}/filter", params={"symbol": "EURUSD"}).json()
    assert body["results_count"] == 5
    assert {trade["symbol"] for trade in body["trades"]} == {"EURUSD"}


def test_by_symbol_groups_trades(client):
    symbols = client.get(f"{API}/by-symbol").json()["symbols"]
    assert {name: stats["trades"] for name, stats in symbols.items()} == {
        "EURUSD": 5,
        "GBPUSD": 3,
        "USDJPY": 2,
    }


def test_upload_valid_report(uploaded_report):
    response = uploaded_report("acceptance_upload.csv", SAMPLE.read_bytes())
    assert response.status_code == 200
    assert response.json()["trades_count"] == 10


def test_upload_rejects_unsupported_extension(uploaded_report):
    assert uploaded_report("notes.txt", b"hello").status_code == 400


@known_bug("KPIs are not rounded (profit_factor 5.833333333333333); contract requires 2 decimals")
def test_kpis_are_rounded_to_two_decimals(client):
    summary = client.get(f"{API}/summary").json()
    assert summary["profit_factor"] == 5.83


@known_bug(
    "max_drawdown_pct can exceed -100% (dashboard showed -3817.3%); percentage base is wrong"
)
def test_drawdown_percentage_is_bounded(client, uploaded_report):
    report = (
        "Open Time,Close Time,Symbol,Type,Volume,Open Price,Close Price,Profit,Comment\n"
        "2025-02-01 09:00:00,2025-02-01 10:00:00,EURUSD,BUY,1.0,1.1000,1.1001,10.0,tiny win\n"
        "2025-02-01 11:00:00,2025-02-01 12:00:00,EURUSD,BUY,1.0,1.1000,1.0960,-400.0,big loss\n"
    )
    uploaded_report("drawdown_case.csv", report.encode())
    summary = client.get(f"{API}/summary").json()
    assert -100.0 <= summary["max_drawdown_pct"] <= 0.0


@known_bug("analytics endpoints are public: no authentication required")
def test_analytics_requires_authentication(client):
    assert client.get(f"{API}/summary").status_code == 401


@known_bug("all users share one dataset: analytics reads the latest file in data/raw/ for everyone")
def test_users_do_not_see_each_others_uploads(client, new_user, uploaded_report):
    _, headers = new_user
    uploaded_report("someone_else.csv", SAMPLE.read_bytes()[:200])
    assert client.get(f"{API}/summary", headers=headers).json()["total_trades"] == 0
