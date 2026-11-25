from fastapi import APIRouter, Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse

from auth_service.adapters.inbound.http.schemas import (
    DeletedOut,
    EmailRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SignInRequest,
    SignUpRequest,
    TokensOut,
    UserEnvelope,
    UserOut,
    VerifyEmailRequest,
)
from auth_service.bootstrap import Container
from auth_service.domain.errors import AuthError
from trading_shared.auth import CurrentUser, current_user_dependency, require_role
from trading_shared.envelope import SuccessResponse, ok
from trading_shared.errors import ErrorBody, ErrorResponse

# Same body for known and unknown emails: no account enumeration.
GENERIC_RESEND_MESSAGE = "If the account exists and is unverified, a new code has been sent."
GENERIC_FORGOT_MESSAGE = "If the account exists, a password reset link has been sent."


def get_container(request: Request) -> Container:
    return request.app.state.container


def register_auth_error_mapping(app: FastAPI) -> None:
    """Render every domain ``AuthError`` with its own code and status (single mapping point)."""

    @app.exception_handler(AuthError)
    async def _auth_error(_: Request, exc: AuthError) -> JSONResponse:
        body = ErrorResponse(error=ErrorBody(code=exc.code, message=str(exc)))
        return JSONResponse(status_code=exc.http_status, content=body.model_dump(mode="json"))


def _current_user(request: Request) -> CurrentUser:
    secret = request.app.state.container.settings.jwt_secret_key.get_secret_value()
    return current_user_dependency(lambda: secret)(request.headers.get("authorization"))


def _require_admin(request: Request) -> CurrentUser:
    user = _current_user(request)
    return require_role(lambda: user, "admin")(user)


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
async def sign_up(
    body: SignUpRequest, container: Container = Depends(get_container)
) -> SuccessResponse[UserEnvelope]:
    user = await container.sign_up.execute(body.email, body.password, body.name)
    envelope = UserEnvelope(user=UserOut.from_domain(user))
    return ok(envelope, container.settings.version, "Account created. Check your email.")


@router.post("/verify-email")
async def verify_email(
    body: VerifyEmailRequest, container: Container = Depends(get_container)
) -> SuccessResponse[None]:
    await container.verify_email.execute(body.email, body.code)
    return ok(None, container.settings.version, "Email verified")


@router.post("/resend-verification")
async def resend_verification(
    body: EmailRequest, container: Container = Depends(get_container)
) -> SuccessResponse[None]:
    await container.resend_verification.execute(body.email)
    return ok(None, container.settings.version, GENERIC_RESEND_MESSAGE)


@router.post("/sign-in")
async def sign_in(
    body: SignInRequest, container: Container = Depends(get_container)
) -> SuccessResponse[TokensOut]:
    tokens = await container.sign_in.execute(body.email, body.password)
    return ok(TokensOut.from_domain(tokens), container.settings.version, "Signed in")


@router.post("/refresh")
async def refresh(
    body: RefreshTokenRequest, container: Container = Depends(get_container)
) -> SuccessResponse[TokensOut]:
    tokens = await container.refresh_session.execute(body.refresh_token)
    return ok(TokensOut.from_domain(tokens), container.settings.version, "Session refreshed")


@router.post("/sign-out")
async def sign_out(
    body: RefreshTokenRequest,
    _: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[None]:
    await container.sign_out.execute(body.refresh_token)
    return ok(None, container.settings.version, "Signed out")


@router.post("/forgot-password")
async def forgot_password(
    body: EmailRequest, container: Container = Depends(get_container)
) -> SuccessResponse[None]:
    await container.forgot_password.execute(body.email)
    return ok(None, container.settings.version, GENERIC_FORGOT_MESSAGE)


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest, container: Container = Depends(get_container)
) -> SuccessResponse[None]:
    await container.reset_password.execute(body.token, body.new_password)
    return ok(None, container.settings.version, "Password updated")


@router.get("/me")
async def me(
    current: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[UserEnvelope]:
    user = await container.get_me.execute(current.id)
    return ok(UserEnvelope(user=UserOut.from_domain(user)), container.settings.version)


@router.delete("/sessions/expired")
async def cleanup_expired_sessions(
    _: CurrentUser = Depends(_require_admin),
    container: Container = Depends(get_container),
) -> SuccessResponse[DeletedOut]:
    deleted = await container.cleanup_expired_sessions.execute()
    return ok(DeletedOut(deleted=deleted), container.settings.version, "Expired sessions removed")
