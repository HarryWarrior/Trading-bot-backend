from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analytics_service.adapters.inbound.http.router import (
    register_analytics_error_mapping,
    router,
)
from analytics_service.application.ports.trade_source import TradeSource
from analytics_service.bootstrap import build_container
from analytics_service.settings import AnalyticsSettings
from trading_shared.errors import register_error_handlers
from trading_shared.logging import configure_logging
from trading_shared.request_id import RequestIdMiddleware


def create_app(
    settings: AnalyticsSettings | None = None, trade_source: TradeSource | None = None
) -> FastAPI:
    settings = settings or AnalyticsSettings()
    configure_logging(settings.log_level)

    app = FastAPI(title=f"{settings.service_name} service", version=settings.version)
    app.state.container = build_container(settings, trade_source)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    register_analytics_error_mapping(app)
    app.include_router(router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": settings.service_name}

    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """Create ``analytics_service.main:app`` lazily so importing the module needs no secrets."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
