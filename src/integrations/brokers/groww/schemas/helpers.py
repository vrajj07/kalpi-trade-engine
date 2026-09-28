"""Groww envelopes: {"status": "SUCCESS", "payload": ...} and {"status": "FAILURE", "error": {...}}."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class GrowwEnvelope(BaseModel, Generic[T]):
    status: str
    payload: T


class GrowwErrorDetail(BaseModel):
    code: str = ""
    message: str = ""


class GrowwError(BaseModel):
    status: str = "FAILURE"
    error: GrowwErrorDetail
