"""SmartAPI envelope: {"status": bool, "message", "errorcode", "data": ...} — also used for errors."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class AngelEnvelope(BaseModel, Generic[T]):
    status: bool
    message: str = ""
    errorcode: str = ""
    data: T


class AngelError(BaseModel):
    status: bool | None = None
    message: str = ""
    errorcode: str = ""
    error_type: str = ""  # set on token failures

    @property
    def code(self) -> str:
        return self.errorcode or self.error_type
