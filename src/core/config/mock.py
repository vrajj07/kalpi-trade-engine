"""Mock broker demo behaviour. Env (JSON), e.g.
MOCK_HOLDINGS='{"INFY": 10}'  MOCK_CASH=50000  MOCK_FAIL='{"TCS": "reject"}'
"""
from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings

from src.integrations.brokers.mock.adapter import FailMode

from .base import env_config


class MockConfig(BaseSettings):
    model_config = env_config("MOCK_")

    holdings: dict[str, int] = Field(default_factory=dict)
    cash: Decimal | None = None  # None: unlimited funds
    fail: dict[str, FailMode] = Field(default_factory=dict)


mock_config = MockConfig()
