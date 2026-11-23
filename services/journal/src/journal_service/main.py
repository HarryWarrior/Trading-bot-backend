from fastapi import FastAPI

from journal_service.adapters.inbound.http.router import router
from journal_service.bootstrap import build_container
from journal_service.settings import JournalSettings
from trading_shared.errors import register_error_handlers
from trading_shared.logging import configure_logging


def create_app(settings: JournalSettings | None = None) -> FastAPI:
    settings = settings or JournalSettings()
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
