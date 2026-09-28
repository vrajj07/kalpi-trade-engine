"""Core application settings, resolved from environment variables (and .env locally).

Integration configs live in sibling modules, one per integration (zerodha.py, fyers.py...),
each exposing a module-level `<name>_config` instance.
"""
from datetime import time

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

    # Empty: execution reports are logged to the console instead.
    notification_webhook_url: str | None = None

    # Execution: how long one order is tracked (status polls / reconciliation by tag)
    # before it is reported as STILL_OPEN or UNCONFIRMED.
    order_timeout_seconds: float = 30.0
    order_poll_interval_seconds: float = 1.0
    # Executions expire at the next market close (IST): order books only cover one day,
    # so a later resume could no longer find already-placed orders by tag.
    market_close_ist: time = time(15, 30)


settings = Settings()
