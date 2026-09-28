"""Fyers credentials. Env: FYERS_API_KEY (the app id, e.g. XXXX-100), FYERS_ACCESS_TOKEN."""
from .base import BrokerConfig, env_config


class FyersConfig(BrokerConfig):
    model_config = env_config("FYERS_")


fyers_config = FyersConfig()
