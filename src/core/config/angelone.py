"""AngelOne credentials. Env: ANGELONE_API_KEY, ANGELONE_ACCESS_TOKEN (jwt), ANGELONE_CLIENT_ID."""
from .base import BrokerConfig, env_config


class AngelOneConfig(BrokerConfig):
    model_config = env_config("ANGELONE_")

    # Sent as X-Client* headers on every SmartAPI call; they identify the calling machine.
    client_local_ip: str = "127.0.0.1"
    client_public_ip: str = "127.0.0.1"
    mac_address: str = "00:00:00:00:00:00"


angelone_config = AngelOneConfig()
