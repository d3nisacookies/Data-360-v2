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

    # Assistant. ollama (local, default) | anthropic | bedrock | vertex | off
    ai_provider: str = "ollama"
    ai_model: str = ""            # blank = qwen2.5:7b for Ollama, claude-sonnet-5-5 for Anthropic; required for Bedrock and Vertex
    ai_redact: bool = True        # replace names, IDs and personal data with tokens before anything reaches the model
    ai_timeout: int = 240         # seconds
    ollama_url: str = "http://ollama:11434"
    anthropic_api_key: str = ""
    aws_region: str = "ap-southeast-1"      # Bedrock; credentials come from the standard AWS chain
    vertex_project: str = ""
    vertex_region: str = "asia-southeast1"  # Vertex; credentials from Google application default credentials


@lru_cache
def get_settings() -> Settings:
    return Settings()
