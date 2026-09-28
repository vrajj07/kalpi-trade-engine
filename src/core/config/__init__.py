"""Core application settings, resolved from environment variables (and .env locally).

Integration configs live in sibling modules, one per integration (zerodha.py, fyers.py...),
each exposing a module-level `<name>_config` instance.
"""
from datetime import time

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    app_name: str = "Kalpi Trade Execution Engine"
    env: str = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    # SecretStr: the URL embeds the DB password, so keep it out of reprs and logs.
    database_url: SecretStr = SecretStr("postgresql+psycopg://kalpi:kalpi@localhost:5433/kalpi")

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value):
        # Hosted Postgres (Render, Heroku...) hands out postgres:// or postgresql:// URLs;
        # SQLAlchemy needs the driver named to pick async psycopg.
        if isinstance(value, str):
            for scheme in ("postgres://", "postgresql://"):
                if value.startswith(scheme):
                    return "postgresql+psycopg://" + value[len(scheme):]
        return value

    # Fernet keys that encrypt stored broker access tokens, comma-separated, newest first.
    # The first encrypts; all decrypt, so a key can be rotated without re-connecting everyone.
    # Generate one: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_keys: SecretStr | None = None

    # Public demo deployments: only the mock broker can be connected. There is no real auth in
    # front of the demo (X-User-Id is trusted), so real broker tokens must never be accepted there.
    mock_only: bool = False

    # Empty: execution reports are logged to the console instead.
    notification_webhook_url: str | None = None
    # Outbox relay. The lease must outlast one delivery (the timeout), or a slow but
    # successful delivery would be claimed and sent again.
    notification_poll_interval_seconds: float = 5.0
    notification_batch_size: int = 20
    notification_timeout_seconds: float = 5.0
    notification_lease_seconds: float = 60.0
    notification_max_attempts: int = 8  # then FAILED (dead-lettered); about 8 minutes of backoff

    # Execution: how long one order is tracked (status polls / reconciliation by tag)
    # before it is reported as STILL_OPEN or UNCONFIRMED.
    order_timeout_seconds: float = 30.0
    order_poll_interval_seconds: float = 1.0
    # Executions expire at the next market close (IST): order books only cover one day,
    # so a later resume could no longer find already-placed orders by tag.
    market_close_ist: time = time(15, 30)


settings = Settings()
