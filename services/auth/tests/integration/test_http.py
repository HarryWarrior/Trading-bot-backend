"""HTTP integration tests against a throwaway MongoDB database and a recording email sender."""

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo import MongoClient

from auth_service.bootstrap import build_container
from auth_service.main import create_app
from auth_service.settings import AuthSettings

MONGO_URL = "mongodb://localhost:27017"
PASSWORD = "Secret123!"
BASE = "/api/v1/auth"


class RecordingEmailSender:
    def __init__(self) -> None:
        self.verifications: list[tuple[str, str]] = []
        self.resets: list[tuple[str, str]] = []

    async def send_verification(self, email: str, code: str) -> None:
        self.verifications.append((email, code))

    async def send_password_reset(self, email: str, token: str) -> None:
        self.resets.append((email, token))


@pytest.fixture
def database_name():
    sync_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=1000)
    try:
        sync_client.admin.command("ping")
    except Exception:
        sync_client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    name = f"test_auth_{uuid.uuid4().hex}"
    try:
        yield name
    finally:
        sync_client.drop_database(name)
        sync_client.close()


@pytest.fixture
def settings(database_name) -> AuthSettings:
    return AuthSettings(
        _env_file=None,
        environment="test",
        mongodb_url=MONGO_URL,
        database_name=database_name,
        jwt_secret_key="test-secret-key-with-enough-length-0123456789",
        refresh_token_days=1,
    )


@pytest.fixture
def sender() -> RecordingEmailSender:
    return RecordingEmailSender()


@pytest.fixture
def client(settings, sender):
    app = create_app(settings, email_sender=sender)
    with TestClient(app) as test_client:
        yield test_client


def _sign_up(client, email="user@mail.com", password=PASSWORD):
    return client.post(
        f"{BASE}/sign-up", json={"email": email, "password": password, "name": "Ana"}
    )


def _verified_sign_in(client, sender, email="user@mail.com"):
    assert _sign_up(client, email).status_code == 201
    code = sender.verifications[-1][1]
    verify = client.post(f"{BASE}/verify-email", json={"email": email, "code": code})
    assert verify.status_code == 200
    response = client.post(f"{BASE}/sign-in", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["data"]


def _bearer(tokens) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_container_accepts_injected_sender(settings, sender):
    container = build_container(settings, email_sender=sender)
    assert container.settings is settings


def test_full_flow(client, sender):
    response = _sign_up(client)
    assert response.status_code == 201
    user = response.json()["data"]["user"]
    assert set(user) == {"id", "email", "name", "role", "email_verified", "created_at"}
    assert user["email_verified"] is False

    sign_in = client.post(f"{BASE}/sign-in", json={"email": "user@mail.com", "password": PASSWORD})
    assert sign_in.status_code == 403
    assert sign_in.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"

    code = sender.verifications[-1][1]
    verify = client.post(f"{BASE}/verify-email", json={"email": "user@mail.com", "code": code})
    assert verify.status_code == 200

    tokens = client.post(
        f"{BASE}/sign-in", json={"email": "  USER@mail.com ", "password": PASSWORD}
    ).json()["data"]
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 900
    assert tokens["user"]["email_verified"] is True

    me = client.get(f"{BASE}/me", headers=_bearer(tokens))
    assert me.status_code == 200
    assert me.json()["data"]["user"]["email"] == "user@mail.com"

    refreshed = client.post(f"{BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()["data"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    reuse = client.post(f"{BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "INVALID_TOKEN"

    sign_out = client.post(
        f"{BASE}/sign-out",
        json={"refresh_token": new_tokens["refresh_token"]},
        headers=_bearer(new_tokens),
    )
    assert sign_out.status_code == 200
    after = client.post(f"{BASE}/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert after.status_code == 401


def test_sign_out_requires_bearer(client, sender):
    tokens = _verified_sign_in(client, sender)
    response = client.post(f"{BASE}/sign-out", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_duplicate_sign_up_with_any_casing_is_409(client):
    assert _sign_up(client, "user@mail.com").status_code == 201
    response = _sign_up(client, "  User@Mail.COM ")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_sign_up_response_has_no_code(client, sender):
    response = _sign_up(client)
    code = sender.verifications[-1][1]
    assert code not in response.text
    assert "code" not in response.json()["data"]


def test_no_response_ever_contains_password_hash(client, sender):
    bodies = [_sign_up(client).text]
    tokens = _verified_sign_in(client, sender, "other@mail.com")
    bodies.append(str(tokens))
    bodies.append(client.get(f"{BASE}/me", headers=_bearer(tokens)).text)
    refreshed = client.post(f"{BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
    bodies.append(refreshed.text)
    bodies.append(
        client.post(f"{BASE}/sign-in", json={"email": "other@mail.com", "password": "x"}).text
    )
    for body in bodies:
        assert "password_hash" not in body
        assert "$2b$" not in body


def test_resend_unknown_email_same_response_as_known(client, sender):
    _sign_up(client)
    known = client.post(f"{BASE}/resend-verification", json={"email": "user@mail.com"})
    unknown = client.post(f"{BASE}/resend-verification", json={"email": "nobody@mail.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json()["data"] == unknown.json()["data"]
    assert known.json()["message"] == unknown.json()["message"]
    assert len(sender.verifications) == 2
    assert sender.verifications[-1][0] == "user@mail.com"


def test_forgot_unknown_email_same_response_as_known(client, sender):
    _sign_up(client)
    known = client.post(f"{BASE}/forgot-password", json={"email": "user@mail.com"})
    unknown = client.post(f"{BASE}/forgot-password", json={"email": "nobody@mail.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json()["data"] == unknown.json()["data"]
    assert known.json()["message"] == unknown.json()["message"]
    assert [email for email, _ in sender.resets] == ["user@mail.com"]


def test_reset_password_revokes_sessions_and_token_is_single_use(client, sender):
    tokens = _verified_sign_in(client, sender)
    client.post(f"{BASE}/forgot-password", json={"email": "user@mail.com"})
    reset_token = sender.resets[-1][1]
    body = {"token": reset_token, "new_password": "NewSecret456!"}
    assert client.post(f"{BASE}/reset-password", json=body).status_code == 200
    again = client.post(f"{BASE}/reset-password", json=body)
    assert again.status_code == 401
    assert again.json()["error"]["code"] == "INVALID_TOKEN"
    stale = client.post(f"{BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert stale.status_code == 401
    sign_in = client.post(
        f"{BASE}/sign-in", json={"email": "user@mail.com", "password": "NewSecret456!"}
    )
    assert sign_in.status_code == 200


def test_wrong_verification_code_is_400(client):
    _sign_up(client)
    body = {"email": "user@mail.com", "code": "000000"}
    response = client.post(f"{BASE}/verify-email", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_VERIFICATION_CODE"


def test_invalid_credentials_is_401(client):
    response = client.post(f"{BASE}/sign-in", json={"email": "no@mail.com", "password": PASSWORD})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_without_token_401(client):
    response = client.get(f"{BASE}/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_cleanup_requires_admin_403(client, sender):
    tokens = _verified_sign_in(client, sender)
    response = client.delete(f"{BASE}/sessions/expired", headers=_bearer(tokens))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_cleanup_as_admin_returns_deleted_count(client, sender, settings):
    _verified_sign_in(client, sender)
    sync_client = MongoClient(MONGO_URL)
    try:
        sync_client[settings.database_name]["users"].update_one(
            {"email": "user@mail.com"}, {"$set": {"role": "admin"}}
        )
    finally:
        sync_client.close()
    admin = client.post(f"{BASE}/sign-in", json={"email": "user@mail.com", "password": PASSWORD})
    response = client.delete(f"{BASE}/sessions/expired", headers=_bearer(admin.json()["data"]))
    assert response.status_code == 200
    assert response.json()["data"]["deleted"] == 0


def test_session_expiry_follows_refresh_token_days(client, sender, settings):
    from datetime import UTC, datetime, timedelta

    _verified_sign_in(client, sender)
    sync_client = MongoClient(MONGO_URL, tz_aware=True)
    try:
        session = sync_client[settings.database_name]["sessions"].find_one()
    finally:
        sync_client.close()
    remaining = session["expires_at"] - datetime.now(UTC)
    assert timedelta(hours=23) < remaining <= timedelta(days=1)


def test_invalid_email_is_422(client):
    response = _sign_up(client, email="not-an-email")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_mixed_case_email_still_works(client, sender):
    assert _sign_up(client, email="Mixed.Case@Mail.COM").status_code == 201
    assert sender.verifications[-1][0] == "mixed.case@mail.com"


def test_smtp_host_without_from_email_fails_settings():
    with pytest.raises(ValidationError):
        AuthSettings(_env_file=None, jwt_secret_key="x", smtp_host="smtp.example.com")


def test_smtp_user_and_password_must_come_together():
    base = {"_env_file": None, "jwt_secret_key": "x", "smtp_host": "h", "smtp_from_email": "a@b.co"}
    with pytest.raises(ValidationError):
        AuthSettings(**base, smtp_user="u")
    with pytest.raises(ValidationError):
        AuthSettings(**base, smtp_password="p")
    assert AuthSettings(**base, smtp_user="u", smtp_password="p").smtp_user == "u"


def test_password_shorter_than_8_is_422(client):
    response = _sign_up(client, password="short")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_password_longer_than_72_bytes_is_422(client):
    assert _sign_up(client, "a@mail.com", "a" * 73).status_code == 422
    assert _sign_up(client, "b@mail.com", "é" * 37).status_code == 422  # 74 bytes
    assert _sign_up(client, "c@mail.com", "a" * 72).status_code == 201


def test_new_password_is_validated_too(client):
    short = client.post(f"{BASE}/reset-password", json={"token": "t", "new_password": "short"})
    assert short.status_code == 422
    long = client.post(f"{BASE}/reset-password", json={"token": "t", "new_password": "a" * 73})
    assert long.status_code == 422


def test_request_id_header_is_echoed(client):
    response = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_prod_without_smtp_fails_settings():
    with pytest.raises(ValidationError):
        AuthSettings(_env_file=None, environment="prod", jwt_secret_key="x")


def test_prod_with_smtp_is_valid():
    settings = AuthSettings(
        _env_file=None,
        environment="prod",
        jwt_secret_key="x",
        smtp_host="smtp.example.com",
        smtp_from_email="no-reply@example.com",
    )
    assert settings.smtp_host == "smtp.example.com"
