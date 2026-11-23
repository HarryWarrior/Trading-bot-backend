from fastapi import FastAPI
from fastapi.testclient import TestClient

from trading_shared.errors import AppError, register_error_handlers


def _build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    async def boom():
        raise AppError("X_CODE", "boom", 409)

    @app.get("/typed")
    async def typed(q: int):
        return {"q": q}

    return app


def test_app_error_rendered_as_envelope():
    response = TestClient(_build_app()).get("/boom")
    assert response.status_code == 409
    assert response.json() == {
        "success": False,
        "error": {"code": "X_CODE", "message": "boom", "details": None},
    }


def test_validation_error_rendered_as_envelope():
    response = TestClient(_build_app()).get("/typed?q=abc")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
