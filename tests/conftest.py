import pytest
from tenacity import wait_none

from src.integrations.brokers.common import client


@pytest.fixture(autouse=True)
def _fresh_rate_limiters():
    # Limiters are process-wide and bound to an event loop; pytest gives each test a new loop.
    client._limiters.clear()


@pytest.fixture(autouse=True)
def _no_retry_backoff(monkeypatch):
    monkeypatch.setattr(client.BaseBrokerClient, "retry_wait", wait_none())
