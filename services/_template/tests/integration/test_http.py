import pytest
from fastapi.testclient import TestClient

from template_service.main import create_app

ITEMS_URL = "/api/v1/template/items"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _as(user_id: str) -> dict[str, str]:
    return {"X-User-Id": user_id}


def test_create_item_returns_201_envelope(client):
    response = client.post(ITEMS_URL, json={"name": "EURUSD"}, headers=_as("a"))
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["name"] == "EURUSD"


def test_missing_user_header_returns_401(client):
    response = client.get(ITEMS_URL)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_blank_name_returns_400(client):
    response = client.post(ITEMS_URL, json={"name": "   "}, headers=_as("a"))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ITEM_NAME"


def test_page_size_over_100_returns_422(client):
    response = client.get(f"{ITEMS_URL}?page_size=101", headers=_as("a"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_paginates(client):
    for name in ("one", "two", "three"):
        client.post(ITEMS_URL, json={"name": name}, headers=_as("a"))

    response = client.get(f"{ITEMS_URL}?page=2&page_size=2", headers=_as("a"))

    data = response.json()["data"]
    assert len(data["items"]) == 1
    assert data["pagination"]["has_prev"] is True
    assert data["pagination"]["has_next"] is False


def test_users_do_not_see_each_other(client):
    client.post(ITEMS_URL, json={"name": "secret"}, headers=_as("a"))

    response = client.get(ITEMS_URL, headers=_as("b"))

    assert response.json()["data"]["items"] == []


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
