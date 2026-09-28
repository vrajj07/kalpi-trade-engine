"""Maps a broker name to its adapter, wired with credentials from settings.

This is the composition root for brokers: the only place that reads broker configuration.
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
from .errors import BrokerNotConfiguredError
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


def get_adapter(broker: BrokerName, credentials: BrokerCredentials | None = None) -> BrokerAdapter:
    try:
        adapter_cls = _ADAPTERS[BrokerName(broker)]
    except (KeyError, ValueError):
        raise ValueError(f"Unsupported broker: {broker}") from None
    return adapter_cls(credentials or credentials_from_settings(BrokerName(broker)))


def credentials_from_settings(broker: BrokerName) -> BrokerCredentials:
    if broker is BrokerName.MOCK:
        mock = mock_config
        return BrokerCredentials(access_token=SecretStr("mock"), extra={"holdings": mock.holdings, "cash": mock.cash, "fail": mock.fail})

    conf = _CONFIGS[broker]
    if conf.access_token is None:
        raise BrokerNotConfiguredError(
            f"{broker} is not configured: set {broker.upper()}_ACCESS_TOKEN", broker=broker
        )
    return BrokerCredentials(
        access_token=conf.access_token,
        api_key=conf.api_key,
        client_id=conf.client_id,
        # Broker-specific extras, e.g. AngelOne's client IP / MAC headers.
        extra=conf.model_dump(exclude={"api_key", "access_token", "client_id"}),
    )


def is_configured(broker: BrokerName) -> bool:
    try:
        credentials_from_settings(broker)
    except BrokerNotConfiguredError:
        return False
    return True
