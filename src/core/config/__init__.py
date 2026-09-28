"""Core application settings, resolved from environment variables (and .env locally).

Integration configs live in sibling modules, one per integration (zerodha.py, fyers.py...),
each exposing a module-level `<name>_config` instance.
"""
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    app_name: str = "Kalpi Trade Execution Engine"
    env: str = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    # SecretStr: the URL embeds the DB password, so keep it out of reprs and logs.
    database_url: SecretStr = SecretStr("postgresql+psycopg://kalpi:kalpi@localhost:5433/kalpi")

    notification_webhook_url: str | None = None


settings = Settings()
