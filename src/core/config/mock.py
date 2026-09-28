"""Mock broker demo behaviour. Env (JSON): MOCK_HOLDINGS='{"INFY": 10}', MOCK_FAIL='{"TCS": "reject"}'."""
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

from .base import env_config


class MockConfig(BaseSettings):
    model_config = env_config("MOCK_")

    holdings: dict[str, int] = Field(default_factory=dict)
    fail: dict[str, Literal["reject", "unavailable", "rate_limit", "unknown"]] = Field(default_factory=dict)


mock_config = MockConfig()
