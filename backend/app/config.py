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

    # Assistant. auto | openrouter | openai | anthropic | bedrock | vertex | off
    # auto = the first key that is set: OPENROUTER_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY.
    ai_provider: str = "auto"
    # blank = openrouter/free (OpenRouter picks a free model that can use tools), gpt-5-mini (OpenAI),
    # claude-sonnet-5-5 (Anthropic); required for Bedrock and Vertex
    ai_model: str = ""
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"  # any OpenAI-compatible service also works
    ai_redact: bool = True        # replace names, IDs and personal data with tokens before anything reaches the model
    ai_timeout: int = 240         # seconds
    anthropic_api_key: str = ""
    aws_region: str = "ap-southeast-1"      # Bedrock; credentials come from the standard AWS chain
    vertex_project: str = ""
    vertex_region: str = "asia-southeast1"  # Vertex; credentials from Google application default credentials


@lru_cache
def get_settings() -> Settings:
    return Settings()
