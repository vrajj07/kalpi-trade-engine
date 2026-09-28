"""Groww app settings. Groww needs none beyond the user's access token."""
from .base import BrokerConfig, env_config


class GrowwConfig(BrokerConfig):
    model_config = env_config("GROWW_")


groww_config = GrowwConfig()
