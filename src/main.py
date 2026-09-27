"""FastAPI app factory and lifespan."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api import router as api_router
from src.core.config import settings
from src.core.database import close_db_connections, init_db
from src.core.logger import configure_logging
from src.middlewares.error_handler import add_error_handlers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    logger.info("Startup complete")
    yield
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
    return app


app = create_app()
