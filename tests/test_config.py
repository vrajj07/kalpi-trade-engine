from pydantic import SecretStr

from src.core.config import settings
from src.core.config.angelone import AngelOneConfig
from src.core.config.mock import MockConfig
from src.core.config.zerodha import ZerodhaConfig
from src.integrations.brokers import registry
from src.integrations.brokers.angelone import AngelOneBroker
from src.integrations.brokers.enums import BrokerName
from src.integrations.brokers.mock import MockBroker
from src.integrations.brokers.registry import credentials_for, get_adapter


def test_broker_config_holds_app_settings_only(monkeypatch):
    monkeypatch.setenv("ZERODHA_API_KEY", "kite-key")
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "must-be-ignored")  # user tokens never come from env
    conf = ZerodhaConfig()
    assert conf.api_key.get_secret_value() == "kite-key"
    assert not hasattr(conf, "access_token")
    assert "kite-key" not in repr(conf)


def test_credentials_combine_app_settings_with_the_users_session(monkeypatch):
    monkeypatch.setitem(registry._CONFIGS, BrokerName.ANGELONE, AngelOneConfig(
        api_key="angel-key", client_public_ip="1.2.3.4"))
    adapter = get_adapter("angelone", credentials_for(BrokerName.ANGELONE, SecretStr("jwt"), client_id="A123"))
    assert isinstance(adapter, AngelOneBroker)
    headers = adapter.client.headers()
    assert (headers["X-PrivateKey"], headers["Authorization"], headers["X-ClientPublicIP"]) == \
        ("angel-key", "Bearer jwt", "1.2.3.4")


def test_mock_credentials_carry_the_demo_behaviour(monkeypatch):
    monkeypatch.setattr(registry, "mock_config", MockConfig(holdings={"INFY": 3}))
    creds = credentials_for(BrokerName.MOCK, SecretStr("any"))
    assert isinstance(get_adapter("mock", creds), MockBroker)
    assert creds.extra["holdings"] == {"INFY": 3}


def test_secrets_are_hidden_from_reprs():
    assert "kalpi:kalpi" not in repr(settings)
    assert "dGVzdC" not in repr(settings)  # the encryption keys
