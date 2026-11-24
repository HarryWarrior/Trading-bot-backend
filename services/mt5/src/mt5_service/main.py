from fastapi import FastAPI

from mt5_service.adapters.inbound.http.router import router
from mt5_service.bootstrap import build_container
from mt5_service.settings import Mt5Settings
from trading_shared.errors import register_error_handlers
from trading_shared.logging import configure_logging


def create_app(settings: Mt5Settings | None = None) -> FastAPI:
    settings = settings or Mt5Settings()
    configure_logging(settings.log_level)

    app = FastAPI(title=f"{settings.service_name} service", version=settings.version)
    app.state.container = build_container(settings)
    register_error_handlers(app)
    app.include_router(router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": settings.service_name}

    return app


app = create_app()
