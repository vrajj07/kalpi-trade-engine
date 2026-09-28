"""Kite envelopes: {"status": "success", "data": ...} and {"status": "error", "error_type": ...}."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class KiteEnvelope(BaseModel, Generic[T]):
    status: str
    data: T


class KiteError(BaseModel):
    error_type: str
    message: str = ""
