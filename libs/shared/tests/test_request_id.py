from fastapi import FastAPI
from fastapi.testclient import TestClient

from trading_shared.request_id import RequestIdMiddleware


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return TestClient(app)


def test_request_id_is_echoed():
    response = _client().get("/ping", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_request_id_is_generated():
    first = _client().get("/ping").headers["X-Request-ID"]
    second = _client().get("/ping").headers["X-Request-ID"]
    assert len(first) == 32
    assert first != second
