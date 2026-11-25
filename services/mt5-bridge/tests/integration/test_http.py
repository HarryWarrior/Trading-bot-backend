import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mt5_bridge_service.main import create_app
from mt5_bridge_service.settings import BridgeSettings

SECRET = "x" * 32


def _settings(**overrides) -> BridgeSettings:
    values = {"jwt_secret_key": SECRET, "ingest_service_key": SECRET, **overrides}
    return BridgeSettings(_env_file=None, **values)


def test_health():
    client = TestClient(create_app(_settings()))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "mt5-bridge"}


def test_defaults_point_at_bridge_db_and_journal():
    settings = _settings()
    assert settings.database_name == "bridge_db"
    assert settings.journal_url == "http://localhost:8002"


def test_mongo_env_names_are_read(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://db:27017")
    monkeypatch.setenv("MONGO_DB", "other_db")
    settings = _settings()
    assert settings.mongodb_url == "mongodb://db:27017"
    assert settings.database_name == "other_db"


@pytest.mark.parametrize("field", ["jwt_secret_key", "ingest_service_key"])
def test_short_secrets_are_rejected(field):
    with pytest.raises(ValidationError):
        _settings(**{field: "short"})
