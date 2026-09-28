"""Zerodha credentials. Env: ZERODHA_API_KEY, ZERODHA_ACCESS_TOKEN."""
from .base import BrokerConfig, env_config


class ZerodhaConfig(BrokerConfig):
    model_config = env_config("ZERODHA_")


zerodha_config = ZerodhaConfig()
