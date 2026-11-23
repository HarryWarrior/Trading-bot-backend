from fastapi import FastAPI

from analytics_service.bootstrap import build_container
from analytics_service.settings import AnalyticsSettings
from trading_shared.errors import register_error_handlers
from trading_shared.logging import configure_logging


def create_app(settings: AnalyticsSettings | None = None) -> FastAPI:
    settings = settings or AnalyticsSettings()
    configure_logging(settings.log_level)

    app = FastAPI(title=f"{settings.service_name} service", version=settings.version)
    app.state.container = build_container(settings)
    register_error_handlers(app)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": settings.service_name}

    return app


app = create_app()
