from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse

from mt5_service.adapters.inbound.http.schemas import (
    AccountEnvelope,
    AccountOut,
    AccountsEnvelope,
    CandleOut,
    RatesOut,
    ResultEnvelope,
    StatusEnvelope,
    StatusOut,
    SyncResultOut,
    UnlinkedOut,
)
from mt5_service.bootstrap import Container
from mt5_service.domain.errors import DomainError
from trading_shared.auth import CurrentUser, current_user_dependency, require_role
from trading_shared.envelope import SuccessResponse, ok
from trading_shared.errors import AppError, ErrorBody, ErrorResponse

router = APIRouter(prefix="/api/v1/mt5", tags=["mt5"])


def get_container(request: Request) -> Container:
    return request.app.state.container


def _current_user(request: Request) -> CurrentUser:
    secret = request.app.state.container.settings.jwt_secret_key.get_secret_value()
    return current_user_dependency(lambda: secret)(request.headers.get("authorization"))


_admin = require_role(_current_user, "admin")


def _verified_token(request: Request, _user: CurrentUser = Depends(_current_user)) -> str:
    """The raw bearer token of the caller, available only after local verification."""
    _, _, token = request.headers["authorization"].partition(" ")
    return token.strip()


def to_app_error(error: DomainError) -> AppError:
    """The single place where domain errors become client-facing errors."""
    return AppError(error.code, str(error), error.http_status)


def register_mt5_error_mapping(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        mapped = to_app_error(exc)
        body = ErrorResponse(error=ErrorBody(code=mapped.code, message=mapped.message))
        return JSONResponse(status_code=mapped.status_code, content=body.model_dump(mode="json"))


@router.post("/accounts/link", status_code=201)
async def link_account(
    response: Response,
    user: CurrentUser = Depends(_admin),
    container: Container = Depends(get_container),
) -> SuccessResponse[AccountEnvelope]:
    """Links the account of the running terminal. Takes no request body."""
    before = {a.id for a in await container.list_accounts.execute(user.id)}
    account = await container.link_account.execute(user.id)
    if account.id in before:
        response.status_code = 200
    return ok(AccountEnvelope(account=AccountOut.from_domain(account)), container.settings.version)


@router.get("/accounts")
async def list_accounts(
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[AccountsEnvelope]:
    accounts = await container.list_accounts.execute(user.id)
    out = AccountsEnvelope(accounts=[AccountOut.from_domain(a) for a in accounts])
    return ok(out, container.settings.version)


@router.get("/accounts/{account_id}/status")
async def account_status(
    account_id: str,
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[StatusEnvelope]:
    status = await container.get_status.execute(user.id, account_id)
    return ok(StatusEnvelope(status=StatusOut.from_domain(status)), container.settings.version)


@router.post("/accounts/{account_id}/sync")
async def sync_account(
    account_id: str,
    user: CurrentUser = Depends(_admin),
    token: str = Depends(_verified_token),
    container: Container = Depends(get_container),
) -> SuccessResponse[ResultEnvelope]:
    result = await container.sync_account.execute(user.id, account_id, token)
    return ok(ResultEnvelope(result=SyncResultOut.from_domain(result)), container.settings.version)


@router.delete("/accounts/{account_id}")
async def unlink_account(
    account_id: str,
    user: CurrentUser = Depends(_admin),
    container: Container = Depends(get_container),
) -> SuccessResponse[UnlinkedOut]:
    await container.unlink_account.execute(user.id, account_id)
    return ok(UnlinkedOut(), container.settings.version)


@router.get("/rates")
async def rates(
    symbol: str = Query(min_length=1, max_length=32),
    timeframe: str = Query(min_length=1, max_length=8),
    count: int = Query(default=500, ge=1, le=1000),
    _user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[RatesOut]:
    candles = await container.get_rates.execute(symbol, timeframe, count)
    out = RatesOut(
        symbol=symbol, timeframe=timeframe, candles=[CandleOut.from_domain(c) for c in candles]
    )
    return ok(out, container.settings.version)
