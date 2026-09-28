import pytest

from src.core.config import settings
from src.core.config.angelone import AngelOneConfig
from src.core.config.mock import MockConfig
from src.core.config.upstox import UpstoxConfig
from src.core.config.zerodha import ZerodhaConfig
from src.integrations.brokers import registry
from src.integrations.brokers.angelone import AngelOneBroker
from src.integrations.brokers.enums import BrokerName
from src.integrations.brokers.errors import BrokerNotConfiguredError
from src.integrations.brokers.mock import MockBroker
from src.integrations.brokers.registry import get_adapter


def test_broker_config_reads_its_env_prefix(monkeypatch):
    monkeypatch.setenv("ZERODHA_API_KEY", "kite-key")
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "kite-token")
    conf = ZerodhaConfig()
    assert conf.access_token.get_secret_value() == "kite-token"
    assert "kite-token" not in repr(conf) and "kite-key" not in repr(conf)


def test_empty_env_value_means_not_configured(monkeypatch):
    # .env.example ships blank values; a blank token must not count as configured.
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")
    monkeypatch.setitem(registry._CONFIGS, BrokerName.UPSTOX, UpstoxConfig())
    with pytest.raises(BrokerNotConfiguredError, match="UPSTOX_ACCESS_TOKEN"):
        get_adapter("upstox")


def test_registry_builds_credentials_from_config(monkeypatch):
    monkeypatch.setitem(registry._CONFIGS, BrokerName.ANGELONE, AngelOneConfig(
        api_key="angel-key", access_token="jwt", client_public_ip="1.2.3.4"))
    adapter = get_adapter("angelone")
    assert isinstance(adapter, AngelOneBroker)
    headers = adapter.client.headers()
    assert (headers["X-PrivateKey"], headers["Authorization"], headers["X-ClientPublicIP"]) == \
        ("angel-key", "Bearer jwt", "1.2.3.4")


def test_mock_needs_no_credentials(monkeypatch):
    monkeypatch.setattr(registry, "mock_config", MockConfig(holdings={"INFY": 3}))
    assert isinstance(get_adapter("mock"), MockBroker)


def test_database_url_is_secret():
    assert "kalpi:kalpi" not in repr(settings)
