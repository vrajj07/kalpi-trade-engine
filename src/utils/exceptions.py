class AppError(Exception):
    """Base class for domain errors that should map to a clean HTTP response."""

    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
