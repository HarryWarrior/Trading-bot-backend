from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from analytics_service.adapters.inbound.http.schemas import (
    BySymbolOut,
    DailyOut,
    DayOut,
    EquityOut,
    EquityPointOut,
    HourlyOut,
    HourOut,
    MonthlyOut,
    MonthOut,
    SummaryEnvelope,
    SummaryOut,
    SymbolOut,
)
from analytics_service.application.ports.trade_source import (
    SourceUnauthenticated,
    SourceUnavailable,
)
from analytics_service.bootstrap import Container
from trading_shared.auth import CurrentUser, current_user_dependency
from trading_shared.envelope import SuccessResponse, ok
from trading_shared.errors import ErrorBody, ErrorResponse

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def get_container(request: Request) -> Container:
    return request.app.state.container


def _current_user(request: Request) -> CurrentUser:
    secret = request.app.state.container.settings.jwt_secret_key.get_secret_value()
    return current_user_dependency(lambda: secret)(request.headers.get("authorization"))


def _verified_token(request: Request, _user: CurrentUser = Depends(_current_user)) -> str:
    """The raw bearer token of the caller, available only after local verification."""
    _, _, token = request.headers["authorization"].partition(" ")
    return token.strip()


def register_analytics_error_mapping(app: FastAPI) -> None:
    @app.exception_handler(SourceUnavailable)
    async def _unavailable(_: Request, __: SourceUnavailable) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(code="JOURNAL_UNAVAILABLE", message="Journal service is unavailable")
        )
        return JSONResponse(status_code=503, content=body.model_dump(mode="json"))

    @app.exception_handler(SourceUnauthenticated)
    async def _unauthenticated(_: Request, __: SourceUnauthenticated) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(code="UNAUTHENTICATED", message="Authentication required")
        )
        return JSONResponse(status_code=401, content=body.model_dump(mode="json"))


@router.get("/summary")
async def summary(
    account_ref: str | None = Query(default=None),
    token: str = Depends(_verified_token),
    container: Container = Depends(get_container),
) -> SuccessResponse[SummaryEnvelope]:
    result = await container.get_summary.execute(token, account_ref)
    return ok(SummaryEnvelope(summary=SummaryOut.from_domain(result)), container.settings.version)


@router.get("/equity")
async def equity(
    account_ref: str | None = Query(default=None),
    token: str = Depends(_verified_token),
    container: Container = Depends(get_container),
) -> SuccessResponse[EquityOut]:
    points = await container.get_series.equity(token, account_ref)
    out = EquityOut(points=[EquityPointOut.from_domain(p) for p in points])
    return ok(out, container.settings.version)


@router.get("/daily")
async def daily(
    account_ref: str | None = Query(default=None),
    token: str = Depends(_verified_token),
    container: Container = Depends(get_container),
) -> SuccessResponse[DailyOut]:
    rows = await container.get_series.daily(token, account_ref)
    return ok(DailyOut(days=[DayOut.from_domain(r) for r in rows]), container.settings.version)


@router.get("/monthly")
async def monthly(
    account_ref: str | None = Query(default=None),
    token: str = Depends(_verified_token),
    container: Container = Depends(get_container),
) -> SuccessResponse[MonthlyOut]:
    rows = await container.get_series.monthly(token, account_ref)
    out = MonthlyOut(months=[MonthOut.from_domain(r) for r in rows])
    return ok(out, container.settings.version)


@router.get("/by-symbol")
async def by_symbol(
    account_ref: str | None = Query(default=None),
    token: str = Depends(_verified_token),
    container: Container = Depends(get_container),
) -> SuccessResponse[BySymbolOut]:
    rows = await container.get_series.by_symbol(token, account_ref)
    out = BySymbolOut(symbols=[SymbolOut.from_domain(r) for r in rows])
    return ok(out, container.settings.version)


@router.get("/hourly")
async def hourly(
    account_ref: str | None = Query(default=None),
    token: str = Depends(_verified_token),
    container: Container = Depends(get_container),
) -> SuccessResponse[HourlyOut]:
    rows = await container.get_series.hourly(token, account_ref)
    return ok(HourlyOut(hours=[HourOut.from_domain(r) for r in rows]), container.settings.version)
