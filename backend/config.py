"""Application configuration loaded from environment / backend/.env."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_name: str = "Insight Flow AI"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # ── CORS ──────────────────────────────────────────────────────────────────
    frontend_url: str = "http://localhost:3000"

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    claude_model: str = "claude-sonnet-4-6"
    claude_max_tokens: int = 4096
    claude_temperature: float = 0.1

    # ── DuckDB limits ─────────────────────────────────────────────────────────
    max_query_rows: int = 50_000
    # Above this row count, switch to sampling instead of full scan
    sample_threshold_rows: int = 500_000
    # Above this row count, use aggregation-first strategy
    large_dataset_threshold_rows: int = 5_000_000
    default_sample_rows: int = 100_000

    # ── File upload ───────────────────────────────────────────────────────────
    max_upload_mb: int = 500
    upload_dir: str = "/tmp/insight_flow_uploads"

    # ── Session ───────────────────────────────────────────────────────────────
    session_ttl_seconds: int = 1_800  # 30 minutes

    # ── Persistence ───────────────────────────────────────────────────────────
    db_path: str = "data/insight_flow.db"


settings = Settings()
