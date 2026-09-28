"""Generic HTTP errors. Modules raise their own domain errors; the service layer converts them
to one of these (see e.g. ExecutionModuleError.to_http_exception), and the error handler
renders every one in the same envelope: {"error": {"code", "message", "details"?}}."""


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, code: str | None = None, details: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnprocessableEntityError(AppError):
    status_code = 422
    code = "unprocessable_entity"


class InternalServerError(AppError):
    status_code = 500
    code = "internal_error"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
