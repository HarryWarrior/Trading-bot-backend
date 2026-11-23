"""Acceptance suite for the legacy API (`app/`).

Runs the real FastAPI app against a throwaway MongoDB database and a temporary
`data/raw/` folder that only contains `sample_trades.csv`, so a run never touches
real users, accounts or reports.

Known bugs are written as ``xfail(strict=True)`` tests describing the CORRECT
behavior. When a bug gets fixed the test XPASSes, the strict mark turns that into
a failure, and whoever fixed it must remove the mark. Run with ``-rxX`` to get the
status report:

    pytest tests/acceptance -rxX
"""

import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_REPORT = REPO_ROOT / "data" / "raw" / "sample_trades.csv"
MONGO_URL = "mongodb://localhost:27017"
PASSWORD = "AcceptancePass123!"


def known_bug(reason: str):
    """Mark a test that describes correct behavior the legacy app does not have yet."""
    return pytest.mark.xfail(strict=True, reason=f"KNOWN BUG: {reason}")


@pytest.fixture(scope="session")
def mongo() -> MongoClient:
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=2000)
    try:
        client.admin.command("ping")
    except PyMongoError:
        pytest.skip("MongoDB is not reachable on localhost:27017")
    return client


@pytest.fixture(scope="session")
def db_name(mongo: MongoClient):
    name = f"acceptance_{uuid.uuid4().hex[:10]}"
    yield name
    mongo.drop_database(name)


@pytest.fixture(scope="session")
def workdir(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("legacy_app")
    (path / "data" / "raw").mkdir(parents=True)
    shutil.copy(SAMPLE_REPORT, path / "data" / "raw" / "sample_trades.csv")
    return path


@pytest.fixture(scope="session")
def client(db_name: str, workdir: Path):
    import os

    from app.config import database

    previous_cwd = os.getcwd()
    database.DATABASE_NAME = db_name
    os.chdir(workdir)
    try:
        from app.main import app

        with TestClient(app) as test_client:
            yield test_client
    finally:
        os.chdir(previous_cwd)


@pytest.fixture(scope="session")
def db(mongo: MongoClient, db_name: str, client):
    return mongo[db_name]


def _register_verified_user(client: TestClient, db) -> tuple[str, str]:
    email = f"user-{uuid.uuid4().hex[:8]}@acceptance-tests.com"
    response = client.post(
        "/api/v1/auth/sign-up", json={"email": email, "password": PASSWORD, "name": "Acceptance"}
    )
    assert response.status_code == 201, response.text
    code = db.verifications.find_one({"identifier": email}, sort=[("created_at", -1)])["code"]
    assert (
        client.post("/api/v1/auth/verify-email", json={"email": email, "code": code}).status_code
        == 200
    )
    response = client.post("/api/v1/auth/sign-in", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return email, response.json()["token"]


@pytest.fixture()
def new_user(client, db):
    """A fresh verified user: returns (email, auth headers)."""
    email, token = _register_verified_user(client, db)
    return email, {"Authorization": f"Bearer {token}"}
