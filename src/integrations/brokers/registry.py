"""Maps a broker name to its adapter, and builds its credentials.

This is the composition root for brokers: the only place that reads broker configuration.
Credentials combine app-level settings (api key, AngelOne's machine headers; from the env)
with the user's own session (access token, client code; from their stored connection).
Adapters themselves take plain BrokerCredentials, so tests can inject fakes.
"""
from pydantic import SecretStr

from src.core.config.angelone import angelone_config
from src.core.config.base import BrokerConfig
from src.core.config.fyers import fyers_config
from src.core.config.groww import groww_config
from src.core.config.mock import mock_config
from src.core.config.upstox import upstox_config
from src.core.config.zerodha import zerodha_config

from .angelone import AngelOneBroker
from .base import BrokerAdapter, BrokerCredentials
from .enums import BrokerName
from .fyers import FyersBroker
from .groww import GrowwBroker
from .mock import MockBroker
from .upstox import UpstoxBroker
from .zerodha import ZerodhaBroker

_ADAPTERS: dict[BrokerName, type[BrokerAdapter]] = {
    cls.name: cls
    for cls in (ZerodhaBroker, FyersBroker, AngelOneBroker, UpstoxBroker, GrowwBroker, MockBroker)
}


_CONFIGS: dict[BrokerName, BrokerConfig] = {
    BrokerName.ZERODHA: zerodha_config,
    BrokerName.FYERS: fyers_config,
    BrokerName.ANGELONE: angelone_config,
    BrokerName.UPSTOX: upstox_config,
    BrokerName.GROWW: groww_config,
}


def supported_brokers() -> list[BrokerName]:
    return sorted(_ADAPTERS)


def get_adapter(broker: BrokerName, credentials: BrokerCredentials) -> BrokerAdapter:
    try:
        adapter_cls = _ADAPTERS[BrokerName(broker)]
    except (KeyError, ValueError):
        raise ValueError(f"Unsupported broker: {broker}") from None
    return adapter_cls(credentials)


def credentials_for(broker: BrokerName, access_token: SecretStr, client_id: str | None = None) -> BrokerCredentials:
    """The user's session (token, client code) plus the app-level settings for this broker."""
    if broker is BrokerName.MOCK:
        mock = mock_config
        return BrokerCredentials(access_token=access_token, client_id=client_id,
                                 extra={"holdings": mock.holdings, "cash": mock.cash, "fail": mock.fail})
    conf = _CONFIGS[broker]
    return BrokerCredentials(
        access_token=access_token,
        api_key=conf.api_key,
        client_id=client_id,
        # Broker-specific extras, e.g. AngelOne's client IP / MAC headers.
        extra=conf.model_dump(exclude={"api_key"}),
    )
