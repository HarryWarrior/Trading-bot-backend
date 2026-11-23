# tests/test_analytics.py

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

SAMPLE_REPORT = Path(__file__).resolve().parents[1] / "data" / "samples" / "sample_trades.csv"

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Run each test in a temp cwd whose data/raw holds only the sample report."""
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    shutil.copy(SAMPLE_REPORT, raw / "sample_trades.csv")
    monkeypatch.chdir(tmp_path)


def test_root_endpoint():
    """Test del endpoint raíz"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "online"
    assert "Trading Portfolio Analytics API" in response.json()["service"]


def test_health_check():
    """Test del health check"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_get_summary():
    """Test summary endpoint returns calculated trade metrics."""
    response = client.get("/api/v1/analytics/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_trades" in data
    assert "win_rate" in data
    assert "profit_factor" in data


def test_get_trades():
    """Test trades collection endpoint returns parsed trades list."""
    response = client.get("/api/v1/analytics/trades")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_symbol_stats():
    """Test symbol breakdown analytics returns per-symbol metrics."""
    response = client.get("/api/v1/analytics/by-symbol")
    assert response.status_code == 200
    data = response.json()
    assert "symbols" in data


# TODO: Agregar tests con datos de prueba
# - Test de upload de CSV
# - Test de cálculo de KPIs
# - Test de filtrado
# - Test de series temporales
