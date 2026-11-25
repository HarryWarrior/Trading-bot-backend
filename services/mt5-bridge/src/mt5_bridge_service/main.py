from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mt5_bridge_service.adapters.inbound.http.router import register_bridge_error_mapping, router
from mt5_bridge_service.application.ports.accounts import AccountRepository
from mt5_bridge_service.application.ports.clock import Clock
from mt5_bridge_service.application.ports.journal import JournalGateway
from mt5_bridge_service.application.ports.tokens import TokenRepository
from mt5_bridge_service.bootstrap import build_container
from mt5_bridge_service.settings import BridgeSettings
from trading_shared.errors import register_error_handlers
from trading_shared.logging import configure_logging
from trading_shared.request_id import RequestIdMiddleware


def create_app(
    settings: BridgeSettings | None = None,
    journal: JournalGateway | None = None,
    tokens: TokenRepository | None = None,
    accounts: AccountRepository | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    settings = settings or BridgeSettings()
    configure_logging(settings.log_level)
    container = build_container(settings, journal, tokens, accounts, clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await container.create_indexes()
        try:
            yield
        finally:
            container.close()

    app = FastAPI(
        title=f"{settings.service_name} service", version=settings.version, lifespan=lifespan
    )
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    register_bridge_error_mapping(app)
    app.include_router(router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": settings.service_name}

    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """Create ``mt5_bridge_service.main:app`` lazily so importing the module needs no secrets."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
