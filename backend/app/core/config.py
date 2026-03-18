"""
Application configuration — loaded once at startup from .env
All settings are validated by Pydantic so a missing required var fails fast.
"""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from repo root (orgmind/.env) regardless of where uvicorn is launched from
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    environment: str = "development"
    demo_mode: bool = True
    extraction_workers: int = 3
    api_url: str = "http://localhost:8000"

    # ── Groq ──────────────────────────────────────────────────────────────────
    groq_api_key: str

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str
    supabase_key: str
    database_url: str

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_uri: str
    neo4j_user: str = "neo4j"
    neo4j_password: str

    # ── Upstash Redis ─────────────────────────────────────────────────────────
    upstash_redis_rest_url: str
    upstash_redis_rest_token: str

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    # ── Integrations (optional) ───────────────────────────────────────────────
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_app_token: str = ""
    notion_token: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
