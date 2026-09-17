from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    project_name: str = "Ondas do Mar API"
    api_v1_str: str = "/api/v1"

    database_url: str = "postgresql+psycopg://ondas:ondas_dev_password@localhost:5432/ondas_do_mar"
    # Dedicated database the test suite provisions and migrates itself (see
    # tests/conftest.py) — kept separate from database_url so pytest never
    # shares state with whatever's sitting in the dev database.
    test_database_url: str = (
        "postgresql+psycopg://ondas:ondas_dev_password@localhost:5432/ondas_do_mar_test"
    )
    backend_cors_origins: list[str] = ["http://localhost:5173"]
    frontend_base_url: str = "http://localhost:5173"

    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    invitation_token_expire_hours: int = 168

    stripe_secret_key: str | None = None
    stripe_publishable_key: str | None = None
    stripe_webhook_secret: str | None = None

    # Generic SMTP — works with Gmail (app password) or any provider, not
    # tied to a specific transactional-email vendor.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "no-reply@ondasdomar.com"
    smtp_from_name: str = "Ondas do Mar"
    smtp_use_tls: bool = True

    media_root: str = "/app/media"
    media_public_base_url: str = "http://localhost:8000/media"

    # How often the background job re-reads every IcalSource's feed and
    # reconciles it into BlockedDate rows (app/core/scheduler.py).
    ical_sync_interval_hours: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
