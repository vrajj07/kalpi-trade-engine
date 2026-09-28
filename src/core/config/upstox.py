"""Upstox credentials. Env: UPSTOX_ACCESS_TOKEN."""
from .base import BrokerConfig, env_config


class UpstoxConfig(BrokerConfig):
    model_config = env_config("UPSTOX_")


upstox_config = UpstoxConfig()
