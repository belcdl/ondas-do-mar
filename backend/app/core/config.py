from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    project_name: str = "Ondas do Mar API"
    api_v1_str: str = "/api/v1"

    database_url: str = "postgresql+psycopg://ondas:ondas_dev_password@localhost:5432/ondas_do_mar"
    backend_cors_origins: list[str] = ["http://localhost:5173"]

    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    invitation_token_expire_hours: int = 168

    stripe_secret_key: str | None = None
    stripe_publishable_key: str | None = None
    stripe_webhook_secret: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
