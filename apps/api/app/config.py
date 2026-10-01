from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+asyncpg://fios:fios@localhost:5432/fios"
    redis_url: str = "redis://localhost:6379/0"

    # local | s3 (ADR-001: local was the Phase-0-slice-1 interim; s3 lands here)
    snapshot_storage_backend: str = "local"
    snapshot_storage_path: str = "./data/bronze"

    # Only read when snapshot_storage_backend == "s3". endpoint_url distinguishes
    # MinIO (http://minio:9000 in Docker, http://localhost:9000 from the host)
    # from real AWS S3/R2 (leave endpoint unset).
    s3_bucket: str | None = None
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"

    # §1: the website (api-football.com) and the API host are different layers —
    # base URLs are explicit config, not something buried in each adapter, so a
    # wrong host is a one-line env fix, not a code change.
    api_football_key: str | None = None
    api_football_base_url: str = "https://v3.football.api-sports.io"
    football_data_token: str | None = None
    football_data_base_url: str = "https://api.football-data.org/v4"

    # Phase 17: settings production must set explicitly (see
    # app.phase17.environments). Comma-separated; never "*" outside
    # development/test because credentials are allowed.
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"
    # Demo fixtures for the legacy Phase 10-16 engines. Off unless explicitly
    # enabled, and refused at startup in staging and production.
    dev_seed: bool = False
    model_artifact_dir: str = "./data/models"
    # Notification channels are only enabled when configured. IN_APP is
    # always available because it is just a database row.
    notification_webhook_url: str | None = None
    notification_smtp_url: str | None = None
    provider_probe_timeout_s: float = 15.0
    # Per-user API budget for mutating ops endpoints (requests per minute).
    api_rate_limit_per_minute: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
