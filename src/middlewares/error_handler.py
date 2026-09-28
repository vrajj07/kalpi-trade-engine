from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.integrations.brokers.errors import (
    BrokerAuthError,
    BrokerError,
    BrokerNotConfiguredError,
    BrokerRateLimitError,
)
from src.utils.exceptions import AppError

# Broker failures reaching the API (e.g. a holdings read). 401/429 describe the broker
# session, not ours; everything else is an upstream failure.
_BROKER_STATUS = {BrokerNotConfiguredError: 400, BrokerAuthError: 401, BrokerRateLimitError: 429}


def add_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        error = {"code": exc.code, "message": exc.message}
        if exc.details:
            error["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content={"error": error})

    @app.exception_handler(BrokerError)
    async def _handle_broker_error(_: Request, exc: BrokerError) -> JSONResponse:
        return JSONResponse(
            status_code=_BROKER_STATUS.get(type(exc), 502),
            content={"error": {"code": type(exc).__name__, "message": exc.message, "broker": exc.broker}},
        )
