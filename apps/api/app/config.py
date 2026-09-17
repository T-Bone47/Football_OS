from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+asyncpg://fios:fios@localhost:5432/fios"
    redis_url: str = "redis://localhost:6379/0"

    # local | s3 — s3 backend lands in Phase 1 (ADR-001)
    snapshot_storage_backend: str = "local"
    snapshot_storage_path: str = "./data/bronze"

    api_football_key: str | None = None
    football_data_org_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
