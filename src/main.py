"""FastAPI app factory and lifespan."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api import router as api_router
from src.core.config import settings
from src.core.database import close_db_connections, init_db
from src.modules.execution.helpers import runner
from src.modules.notification import NotificationModule
from src.core.logger import configure_logging
from src.middlewares.error_handler import add_error_handlers

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    NotificationModule.start_relay()
    logger.info("Startup complete")
    yield
    await runner.shutdown()  # before the engine goes: running executions still hold sessions
    await NotificationModule.stop_relay()
    await close_db_connections()


def create_app() -> FastAPI:
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )
    add_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    # Demo UI: a static page on the same origin, so no CORS. It calls the API like any other client.
    app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    return app


app = create_app()
