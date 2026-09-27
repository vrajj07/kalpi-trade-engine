from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Kalpi Trade Execution Engine"
    env: str = "local"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./data/kalpi.db"

    notification_webhook_url: str | None = None


settings = Settings()
