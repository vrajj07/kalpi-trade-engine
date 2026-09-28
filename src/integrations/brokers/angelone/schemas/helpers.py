"""SmartAPI envelope: {"status": bool, "message", "errorcode", "data": ...} — also used for errors."""
from typing import Generic, TypeVar

from pydantic import AliasChoices, BaseModel, Field

T = TypeVar("T")


class AngelEnvelope(BaseModel, Generic[T]):
    status: bool
    message: str = ""
    errorcode: str = ""
    data: T


class AngelError(BaseModel):
    """Both error shapes Angel sends: {"status": false, "errorcode"} for most failures, and
    {"success": false, "errorCode": "AG8001", "data": ""} for token failures."""
    status: bool | None = None
    success: bool | None = None
    message: str = ""
    errorcode: str = Field(default="", validation_alias=AliasChoices("errorcode", "errorCode"))
    error_type: str = ""  # set on token failures

    @property
    def failed(self) -> bool:
        return self.status is False or self.success is False

    @property
    def code(self) -> str:
        return self.errorcode or self.error_type
