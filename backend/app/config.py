"""Runtime settings, read from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Data360"
    environment: str = "development"  # development | production

    database_url: str = "postgresql+psycopg://data360:data360@localhost:5432/data360"

    # Auth. JWT_SECRET must be set to a long random value in production.
    jwt_secret: str = "change-me-in-production"
    jwt_expiry_minutes: int = 8 * 60
    admin_email: str = "admin@data360.local"
    admin_password: str = "admin12345"

    # Where uploaded source files are kept (a Docker volume in compose).
    storage_dir: str = "./storage"
    max_upload_mb: int = 50

    # Records older than this many days count as stale.
    stale_days: int = 90
    # Reference date for timeliness, YYYY-MM-DD. Empty = today.
    reference_date: str = ""

    cors_origins: str = "http://localhost:5173,http://localhost:8080"


@lru_cache
def get_settings() -> Settings:
    return Settings()
