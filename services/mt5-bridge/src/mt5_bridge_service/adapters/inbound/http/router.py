"""HTTP routes of the bridge.

EA-facing (``Authorization: Bearer <ingest token>``): ``/ingest/deals``, ``/ingest/heartbeat``.
User-facing (JWT from auth): ``/tokens``, ``/accounts``, ``/ea/download``.
"""

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from mt5_bridge_service.adapters.inbound.http.dependencies import get_container
from mt5_bridge_service.adapters.inbound.http.schemas import (
    AccountEnvelope,
    AccountOut,
    AccountsEnvelope,
    CreatedTokenOut,
    CreateTokenIn,
    HeartbeatIn,
    IngestDealsIn,
    IngestDealsOut,
    TokenEnvelope,
    TokenOut,
    TokensEnvelope,
)
from mt5_bridge_service.adapters.inbound.http.token_auth import ingest_token_owner
from mt5_bridge_service.bootstrap import Container
from mt5_bridge_service.domain.account import AccountStatus
from mt5_bridge_service.domain.errors import DomainError
from mt5_bridge_service.domain.token import IngestToken
from trading_shared.auth import CurrentUser, current_user_dependency
from trading_shared.envelope import SuccessResponse, ok
from trading_shared.errors import AppError, ErrorBody, ErrorResponse

EA_DOWNLOAD_NAME = "TradingJournalBridge.ex5"

router = APIRouter(prefix="/api/v1/mt5-bridge", tags=["mt5-bridge"])


def _current_user(request: Request) -> CurrentUser:
    secret = request.app.state.container.settings.jwt_secret_key.get_secret_value()
    return current_user_dependency(lambda: secret)(request.headers.get("authorization"))


def to_app_error(error: DomainError) -> AppError:
    """The single place where domain errors become client-facing errors."""
    return AppError(error.code, str(error), error.http_status, getattr(error, "details", None))


def register_bridge_error_mapping(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        mapped = to_app_error(exc)
        body = ErrorResponse(
            error=ErrorBody(code=mapped.code, message=mapped.message, details=mapped.details)
        )
        return JSONResponse(status_code=mapped.status_code, content=body.model_dump(mode="json"))


# --- EA-facing ------------------------------------------------------------------------------


@router.post("/ingest/deals")
async def ingest_deals(
    body: IngestDealsIn,
    token: IngestToken = Depends(ingest_token_owner),
    container: Container = Depends(get_container),
) -> SuccessResponse[IngestDealsOut]:
    """503 means "keep the batch and retry"; 422 means "this batch can never be accepted"."""
    result = await container.ingest_deals.execute(
        token.user_id, body.account_login, body.server, [d.to_domain() for d in body.deals]
    )
    return ok(IngestDealsOut.from_domain(result), container.settings.version, "Deals ingested")


@router.post("/ingest/heartbeat")
async def ingest_heartbeat(
    body: HeartbeatIn,
    token: IngestToken = Depends(ingest_token_owner),
    container: Container = Depends(get_container),
) -> SuccessResponse[AccountEnvelope]:
    account = await container.record_heartbeat.execute(token.user_id, body.to_domain())
    out = AccountOut.from_domain(account, AccountStatus.CONNECTED.value)
    return ok(AccountEnvelope(account=out), container.settings.version, "Heartbeat recorded")


# --- user-facing ----------------------------------------------------------------------------


@router.post("/tokens", status_code=201)
async def create_token(
    body: CreateTokenIn,
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[CreatedTokenOut]:
    token, plaintext = await container.issue_token.execute(user.id, body.name)
    out = CreatedTokenOut(token=TokenOut.from_domain(token), plaintext_token=plaintext)
    return ok(out, container.settings.version, "Token created; it is shown only once")


@router.get("/tokens")
async def list_tokens(
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[TokensEnvelope]:
    tokens = await container.list_tokens.execute(user.id)
    out = TokensEnvelope(tokens=[TokenOut.from_domain(t) for t in tokens])
    return ok(out, container.settings.version)


@router.delete("/tokens/{token_id}")
async def revoke_token(
    token_id: str,
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[TokenEnvelope]:
    token = await container.revoke_token.execute(user.id, token_id)
    out = TokenEnvelope(token=TokenOut.from_domain(token))
    return ok(out, container.settings.version, "Token revoked")


@router.get("/accounts")
async def list_accounts(
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[AccountsEnvelope]:
    overviews = await container.list_accounts.execute(user.id)
    out = AccountsEnvelope(accounts=[AccountOut.from_overview(o) for o in overviews])
    return ok(out, container.settings.version)


@router.get("/ea/download", response_model=None)
async def download_ea(
    _user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> FileResponse:
    path = container.settings.ea_file_path
    if not path.is_file():
        raise AppError("NOT_FOUND", "The EA has not been built yet", 404)
    return FileResponse(path, media_type="application/octet-stream", filename=EA_DOWNLOAD_NAME)
