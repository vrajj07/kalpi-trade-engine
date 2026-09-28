"""Base for broker configs: credentials resolved from env vars under a per-broker prefix."""
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def env_config(prefix: str) -> SettingsConfigDict:
    # env_ignore_empty: a blank `KEY=` (as in .env.example) means unset, not an empty secret.
    return SettingsConfigDict(env_prefix=prefix, env_file=".env", env_ignore_empty=True, extra="ignore")


class BrokerConfig(BaseSettings):
    """App-level settings only: they identify Kalpi's registered app to the broker.

    User-level credentials (access token, client code) are never read from the environment:
    each user connects their own account, stored encrypted in broker_connections.
    """

    api_key: SecretStr | None = None
