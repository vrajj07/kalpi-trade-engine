import os
import tempfile

# API tests run against a throwaway SQLite file; set before any src module reads settings.
# Tests that set MockConfig pass _env_file=None: pydantic-settings deep-merges dict fields
# across sources, so .env MOCK_HOLDINGS would otherwise leak into holdings={...}.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["ORDER_TIMEOUT_SECONDS"] = "0.2"
os.environ["ORDER_POLL_INTERVAL_SECONDS"] = "0.01"
os.environ["NOTIFICATION_POLL_INTERVAL_SECONDS"] = "0.05"
os.environ["TOKEN_ENCRYPTION_KEYS"] = "dGVzdC1vbmx5LWtleS1ub3QtYS1zZWNyZXQtMzJieXQ="  # Fernet key, tests only

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
