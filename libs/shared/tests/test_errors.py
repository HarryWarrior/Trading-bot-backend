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


def _build_app_with_failures() -> FastAPI:
    from fastapi import HTTPException
    from pydantic import BaseModel, field_validator

    class Login(BaseModel):
        email: str
        password: str

        @field_validator("email")
        @classmethod
        def must_have_at(cls, value: str) -> str:
            if "@" not in value:
                raise ValueError("invalid email")
            return value

    app = FastAPI()
    register_error_handlers(app)

    @app.post("/login")
    async def login(body: Login):
        return {"ok": True}

    @app.get("/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="nope")

    @app.get("/crash")
    async def crash():
        raise RuntimeError("boom")

    return app


def test_custom_validator_error_rendered_as_422_envelope():
    response = TestClient(_build_app_with_failures()).post(
        "/login", json={"email": "bad", "password": "s3cret"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validation_details_do_not_echo_input():
    response = TestClient(_build_app_with_failures()).post(
        "/login", json={"email": "bad", "password": "s3cret"}
    )
    assert "s3cret" not in response.text
    assert all("input" not in detail for detail in response.json()["error"]["details"])


def test_unknown_route_rendered_as_not_found_envelope():
    response = TestClient(_build_app_with_failures()).get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_http_exception_rendered_as_envelope():
    response = TestClient(_build_app_with_failures()).get("/forbidden")
    assert response.status_code == 403
    assert response.json()["error"] == {"code": "FORBIDDEN", "message": "nope", "details": None}


def test_unhandled_exception_rendered_as_internal_error_envelope():
    client = TestClient(_build_app_with_failures(), raise_server_exceptions=False)
    response = client.get("/crash")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "boom" not in response.text
