from fastapi import FastAPI

from app.api import brokers, executions, health
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version="0.1.0")
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(brokers.router, prefix="/api/v1/brokers", tags=["brokers"])
    app.include_router(executions.router, prefix="/api/v1/executions", tags=["executions"])
    return app


app = create_app()
