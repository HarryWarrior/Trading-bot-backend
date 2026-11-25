import hmac
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, FastAPI, File, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse

from journal_service.adapters.inbound.http.schemas import (
    AccountList,
    AccountOut,
    BalanceEventOut,
    DatasetOut,
    ImportEnvelope,
    ImportOut,
    IngestDealsOut,
    IngestDealsRequest,
    IngestOut,
    IngestRequest,
    SkippedPositionOut,
    TradeEnvelope,
    TradeOut,
)
from journal_service.application.ports.parsing import ParsedBalanceEvent, ParsedTrade
from journal_service.application.ports.repositories import TradeFilters
from journal_service.bootstrap import Container
from journal_service.domain.deals import RawDeal
from journal_service.domain.errors import DomainError, DuplicateImport, UnreadableReport
from journal_service.domain.trade import Outcome, Side
from trading_shared.auth import CurrentUser, current_user_dependency
from trading_shared.envelope import (
    Page,
    PageParams,
    SuccessResponse,
    build_pagination,
    ok,
)
from trading_shared.errors import AppError, ErrorBody, ErrorResponse
from trading_shared.http import page_params

ALLOWED_EXTENSIONS = (".csv", ".xlsx", ".xls")
TRADE_SORT_FIELDS = ("close_time", "open_time", "profit", "symbol")
BYTES_PER_MB = 1024 * 1024


def get_container(request: Request) -> Container:
    return request.app.state.container


def _error_details(exc: DomainError) -> dict[str, str] | None:
    if isinstance(exc, DuplicateImport):
        return {"import_id": exc.import_id}
    if isinstance(exc, UnreadableReport):
        return {"reason": exc.reason}
    return None


def register_journal_error_mapping(app: FastAPI) -> None:
    """Render every domain error with its own code and status (single mapping point)."""

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(code=exc.code, message=str(exc), details=_error_details(exc))
        )
        return JSONResponse(status_code=exc.http_status, content=body.model_dump(mode="json"))


def _current_user(request: Request) -> CurrentUser:
    secret = request.app.state.container.settings.jwt_secret_key.get_secret_value()
    return current_user_dependency(lambda: secret)(request.headers.get("authorization"))


def _require_service_key(request: Request) -> None:
    """Machine-to-machine guard: checks ``X-Service-Key`` before the body is parsed."""
    expected = request.app.state.container.settings.ingest_service_key.get_secret_value()
    given = request.headers.get("x-service-key", "")
    if not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
        raise AppError("FORBIDDEN", "A valid service key is required", status.HTTP_403_FORBIDDEN)


def _service_key(request: Request, _user: CurrentUser = Depends(_current_user)) -> None:
    """Guard for ``/ingest/mt5``: authentication first, then the service key."""
    _require_service_key(request)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _trade_page_params(params: PageParams = Depends(page_params)) -> PageParams:
    if params.sort_by is not None and params.sort_by not in TRADE_SORT_FIELDS:
        raise AppError(
            "VALIDATION_ERROR",
            f"sort_by must be one of: {', '.join(TRADE_SORT_FIELDS)}",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return params


def _trade_filters(
    symbol: str | None = Query(default=None),
    outcome: Outcome | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    profit_min: Decimal | None = Query(default=None),
    profit_max: Decimal | None = Query(default=None),
    account_ref: str | None = Query(default=None),
) -> TradeFilters:
    return TradeFilters(
        symbol=symbol,
        outcome=outcome,
        date_from=_aware(date_from),
        date_to=_aware(date_to),
        profit_min=profit_min,
        profit_max=profit_max,
        account_ref=account_ref,
    )


router = APIRouter(prefix="/api/v1/journal", tags=["journal"])


@router.post("/imports", status_code=status.HTTP_201_CREATED)
async def upload_import(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[ImportEnvelope]:
    filename = file.filename or ""
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise AppError("UNSUPPORTED_FILE", "Only .csv, .xlsx and .xls files are supported", 400)
    limit = container.settings.max_upload_mb * BYTES_PER_MB
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise AppError(
            "FILE_TOO_LARGE", f"File exceeds the {container.settings.max_upload_mb} MB limit", 413
        )
    report = await container.import_report.execute(user.id, filename, content)
    envelope = ImportEnvelope(import_=ImportOut.from_domain(report))
    return ok(envelope, container.settings.version, "Report imported")


@router.get("/imports")
async def list_imports(
    params: PageParams = Depends(page_params),
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[Page[ImportOut]]:
    items, total = await container.list_imports.execute(user.id, params)
    page = Page[ImportOut](
        items=[ImportOut.from_domain(i) for i in items],
        pagination=build_pagination(params.page, params.page_size, total),
    )
    return ok(page, container.settings.version)


@router.get("/trades")
async def list_trades(
    params: PageParams = Depends(_trade_page_params),
    filters: TradeFilters = Depends(_trade_filters),
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[Page[TradeOut]]:
    items, total = await container.list_trades.execute(user.id, filters, params)
    page = Page[TradeOut](
        items=[TradeOut.from_domain(t) for t in items],
        pagination=build_pagination(params.page, params.page_size, total),
    )
    return ok(page, container.settings.version)


@router.get("/trades/{trade_id}")
async def get_trade(
    trade_id: str,
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[TradeEnvelope]:
    trade = await container.get_trade.execute(user.id, trade_id)
    return ok(TradeEnvelope(trade=TradeOut.from_domain(trade)), container.settings.version)


@router.get("/accounts")
async def list_accounts(
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[AccountList]:
    accounts = await container.list_accounts.execute(user.id)
    return ok(
        AccountList(items=[AccountOut.from_domain(a) for a in accounts]),
        container.settings.version,
    )


@router.get("/dataset")
async def get_dataset(
    account_ref: str | None = Query(default=None),
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[DatasetOut]:
    dataset = await container.get_dataset.execute(user.id, account_ref)
    out = DatasetOut(
        trades=[TradeOut.from_domain(t) for t in dataset.trades],
        balance_events=[BalanceEventOut.from_domain(e) for e in dataset.balance_events],
    )
    return ok(out, container.settings.version)


@router.post("/ingest/mt5", dependencies=[Depends(_service_key)])
async def ingest_mt5(
    body: IngestRequest,
    user: CurrentUser = Depends(_current_user),
    container: Container = Depends(get_container),
) -> SuccessResponse[IngestOut]:
    trades = [
        ParsedTrade(
            position_id=t.position_id,
            symbol=t.symbol,
            side=Side(t.side),
            volume=t.volume,
            open_time=t.open_time,
            close_time=t.close_time,
            open_price=t.open_price,
            close_price=t.close_price,
            stop_loss=t.stop_loss,
            take_profit=t.take_profit,
            commission=t.commission,
            swap=t.swap,
            profit=t.profit,
            comment=t.comment,
        )
        for t in body.trades
    ]
    events = [
        ParsedBalanceEvent(
            kind=e.kind, amount=e.amount, time=e.time, source_ref=e.source_ref, comment=e.comment
        )
        for e in body.balance_events
    ]
    result = await container.ingest_mt5.execute(user.id, body.account_ref, trades, events)
    return ok(
        IngestOut(
            created=result.created, updated=result.updated, balance_events=result.balance_events
        ),
        container.settings.version,
        "History ingested",
    )


@router.post("/ingest/deals", dependencies=[Depends(_require_service_key)])
async def ingest_deals(
    body: IngestDealsRequest,
    container: Container = Depends(get_container),
) -> SuccessResponse[IngestDealsOut]:
    """Raw MT5 deals from the EA bridge. Service key only: the bridge names the owner in the body."""
    deals = [
        RawDeal(
            ticket=d.ticket,
            position_id=d.position_id,
            time=d.time,
            type=d.type,
            entry=d.entry,
            symbol=d.symbol,
            volume=d.volume,
            price=d.price,
            commission=d.commission,
            swap=d.swap,
            profit=d.profit,
            sl=d.sl,
            tp=d.tp,
            comment=d.comment,
            fee=d.fee,
        )
        for d in body.deals
    ]
    result = await container.ingest_deals.execute(body.user_id, body.account_ref, deals)
    out = IngestDealsOut(
        received=result.received,
        new=result.new,
        trades_upserted=result.trades_upserted,
        balance_events=result.balance_events,
        skipped=[SkippedPositionOut(position_id=p, reason=r) for p, r in result.skipped],
    )
    return ok(out, container.settings.version, "Deals ingested")
