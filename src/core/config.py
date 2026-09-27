from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Kalpi Trade Execution Engine"
    env: str = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://kalpi:kalpi@localhost:5433/kalpi"

    notification_webhook_url: str | None = None


settings = Settings()
