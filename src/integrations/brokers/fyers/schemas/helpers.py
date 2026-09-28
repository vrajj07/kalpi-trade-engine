"""Fyers has no data wrapper: every body carries {"s": "ok"|"error", "code", "message"} at the top level."""
from pydantic import BaseModel


class FyersStatus(BaseModel):
    s: str
    code: int | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.s == "ok"
