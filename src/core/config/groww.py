"""Groww credentials. Env: GROWW_ACCESS_TOKEN."""
from .base import BrokerConfig, env_config


class GrowwConfig(BrokerConfig):
    model_config = env_config("GROWW_")


groww_config = GrowwConfig()
