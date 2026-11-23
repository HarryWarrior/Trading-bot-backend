from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from trading_shared.auth import (
    CurrentUser,
    current_user_dependency,
    decode_access_token,
    require_role,
)
from trading_shared.errors import AppError, register_error_handlers

SECRET = "test-secret-with-enough-length-for-hs256"


def _token(secret: str = SECRET, algorithm: str = "HS256", expires_in: int = 900, **claims) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "user-1",
        "email": "user@mail.com",
        "role": "user",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    } | claims
    return jwt.encode(payload, secret, algorithm=algorithm)


def _build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    get_user = current_user_dependency(lambda: SECRET)

    @app.get("/me")
    async def me(user: CurrentUser = Depends(get_user)):
        return {"id": user.id, "email": user.email, "role": user.role}

    @app.get("/admin")
    async def admin(user: CurrentUser = Depends(require_role(get_user, "admin"))):
        return {"id": user.id}

    return app


def test_valid_token_returns_current_user():
    assert decode_access_token(_token(), SECRET) == CurrentUser(
        id="user-1", email="user@mail.com", role="user"
    )


def test_expired_token_is_rejected():
    with pytest.raises(AppError) as exc:
        decode_access_token(_token(expires_in=-10), SECRET)
    assert exc.value.code == "UNAUTHENTICATED"
    assert exc.value.status_code == 401


def test_wrong_secret_is_rejected():
    with pytest.raises(AppError) as exc:
        decode_access_token(_token(secret="another-secret-with-enough-length-x"), SECRET)
    assert exc.value.code == "UNAUTHENTICATED"


def test_alg_none_is_rejected():
    token = jwt.encode({"sub": "u", "email": "e", "role": "admin"}, None, algorithm="none")
    with pytest.raises(AppError) as exc:
        decode_access_token(token, SECRET)
    assert exc.value.code == "UNAUTHENTICATED"


def test_missing_claims_are_rejected():
    token = jwt.encode({"sub": "u", "exp": datetime.now(UTC) + timedelta(minutes=5)}, SECRET)
    with pytest.raises(AppError) as exc:
        decode_access_token(token, SECRET)
    assert exc.value.code == "UNAUTHENTICATED"


def test_dependency_accepts_bearer_token():
    response = TestClient(_build_app()).get("/me", headers={"Authorization": f"Bearer {_token()}"})
    assert response.status_code == 200
    assert response.json()["email"] == "user@mail.com"


def test_missing_header_returns_401_envelope():
    response = TestClient(_build_app()).get("/me")
    assert response.status_code == 401
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_non_bearer_header_returns_401():
    response = TestClient(_build_app()).get("/me", headers={"Authorization": "Basic abc"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_require_role_rejects_other_roles():
    response = TestClient(_build_app()).get(
        "/admin", headers={"Authorization": f"Bearer {_token(role='user')}"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_require_role_allows_matching_role():
    response = TestClient(_build_app()).get(
        "/admin", headers={"Authorization": f"Bearer {_token(role='admin')}"}
    )
    assert response.status_code == 200


@pytest.mark.parametrize("secret", ["", "   "])
def test_empty_secret_is_rejected(secret):
    token = jwt.encode({"sub": "u", "email": "e", "role": "admin"}, secret, algorithm="HS256")
    with pytest.raises(ValueError, match="secret"):
        decode_access_token(token, secret)


def test_empty_secret_in_dependency_returns_500_not_200():
    app = FastAPI()
    register_error_handlers(app)
    get_user = current_user_dependency(lambda: "")

    @app.get("/me")
    async def me(user: CurrentUser = Depends(get_user)):
        return {"id": user.id}

    token = jwt.encode({"sub": "u", "email": "e", "role": "admin"}, "", algorithm="HS256")
    response = TestClient(app, raise_server_exceptions=False).get(
        "/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
