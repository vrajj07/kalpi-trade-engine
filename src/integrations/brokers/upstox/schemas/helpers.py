"""Upstox envelopes: {"status": "success", "data": ...} and {"status": "error", "errors": [...]}."""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class UpstoxEnvelope(BaseModel, Generic[T]):
    status: str
    data: T


class UpstoxErrorDetail(BaseModel):
    errorCode: str = ""
    message: str = ""


class UpstoxError(BaseModel):
    errors: list[UpstoxErrorDetail] = Field(min_length=1)

    @property
    def first(self) -> UpstoxErrorDetail:
        return self.errors[0]
