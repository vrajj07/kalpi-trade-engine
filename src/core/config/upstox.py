"""Upstox app settings. Upstox needs none beyond the user's access token."""
from .base import BrokerConfig, env_config


class UpstoxConfig(BrokerConfig):
    model_config = env_config("UPSTOX_")


upstox_config = UpstoxConfig()
