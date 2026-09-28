"""Base for broker configs: credentials resolved from env vars under a per-broker prefix."""
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def env_config(prefix: str) -> SettingsConfigDict:
    # env_ignore_empty: a blank `KEY=` (as in .env.example) means unset, not an empty secret.
    return SettingsConfigDict(env_prefix=prefix, env_file=".env", env_ignore_empty=True, extra="ignore")


class BrokerConfig(BaseSettings):
    """Access tokens are short-lived (most brokers expire them daily). Obtaining them through
    each broker's login flow is out of scope, so they are supplied here and rotated out of band.
    One set per broker means one trading account per deployment; a multi-user system would
    keep per-user tokens in a secrets store instead.
    """

    api_key: SecretStr | None = None
    access_token: SecretStr | None = None
    client_id: str | None = None
