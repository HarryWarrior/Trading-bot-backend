"""Acceptance: authentication flows of the legacy API (`/api/v1/auth`)."""

import uuid

from tests.acceptance.conftest import PASSWORD, known_bug

AUTH = "/api/v1/auth"


def _email() -> str:
    return f"user-{uuid.uuid4().hex[:8]}@acceptance-tests.com"


def test_health(client):
    assert client.get("/health").json()["status"] == "healthy"


def test_sign_up_creates_unverified_user(client, db):
    email = _email()
    response = client.post(
        f"{AUTH}/sign-up", json={"email": email, "password": PASSWORD, "name": "A"}
    )
    assert response.status_code == 201
    assert db.users.find_one({"email": email})["email_verified"] is False


def test_duplicate_email_is_rejected(client, new_user):
    email, _ = new_user
    response = client.post(
        f"{AUTH}/sign-up", json={"email": email, "password": PASSWORD, "name": "A"}
    )
    assert response.status_code == 400


def test_unverified_user_cannot_sign_in(client):
    email = _email()
    client.post(f"{AUTH}/sign-up", json={"email": email, "password": PASSWORD, "name": "A"})
    assert (
        client.post(f"{AUTH}/sign-in", json={"email": email, "password": PASSWORD}).status_code
        == 403
    )


def test_wrong_verification_code_is_rejected(client):
    email = _email()
    client.post(f"{AUTH}/sign-up", json={"email": email, "password": PASSWORD, "name": "A"})
    response = client.post(f"{AUTH}/verify-email", json={"email": email, "code": "000000"})
    assert response.status_code == 400


def test_verified_user_gets_session(client, new_user):
    email, headers = new_user
    assert client.get(f"{AUTH}/session", headers=headers).json()["user"]["email"] == email
    assert client.get(f"{AUTH}/users/me", headers=headers).json()["email"] == email


def test_wrong_password_is_rejected(client, new_user):
    email, _ = new_user
    assert (
        client.post(
            f"{AUTH}/sign-in", json={"email": email, "password": "Wrong-Pass-1"}
        ).status_code
        == 401
    )


def test_invalid_token_is_rejected(client):
    assert (
        client.get(f"{AUTH}/session", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )


def test_sign_out_invalidates_token(client, new_user):
    _, headers = new_user
    assert client.post(f"{AUTH}/sign-out", headers=headers).status_code == 200
    assert client.get(f"{AUTH}/session", headers=headers).status_code == 401


def test_session_cleanup_requires_admin(client, new_user):
    _, headers = new_user
    assert client.delete(f"{AUTH}/sessions/cleanup", headers=headers).status_code == 403


def test_reset_password_with_invalid_token_is_rejected(client):
    response = client.post(
        f"{AUTH}/reset-password", json={"token": "invalid", "new_password": "Another123!"}
    )
    assert response.status_code == 400


def test_forgot_password_does_not_reveal_unknown_emails(client):
    assert client.post(f"{AUTH}/forgot-password", json={"email": _email()}).status_code == 200


@known_bug(
    "sign-up returns the email verification code in the response, bypassing email verification"
)
def test_sign_up_does_not_expose_verification_code(client):
    response = client.post(
        f"{AUTH}/sign-up", json={"email": _email(), "password": PASSWORD, "name": "A"}
    )
    assert "verification_code" not in response.json()


@known_bug("resend-verification returns the verification code in the response")
def test_resend_verification_does_not_expose_code(client):
    email = _email()
    client.post(f"{AUTH}/sign-up", json={"email": email, "password": PASSWORD, "name": "A"})
    response = client.post(f"{AUTH}/resend-verification", params={"email": email})
    assert "verification_code" not in response.json()


@known_bug("OAuth providers (Google/GitHub) are not implemented (501)")
def test_oauth_google_redirects_to_provider(client):
    response = client.get(f"{AUTH}/oauth/google", follow_redirects=False)
    assert response.status_code in (302, 307)
