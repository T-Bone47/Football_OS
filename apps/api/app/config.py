from functools import lru_cache
from typing import Literal

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
    # The free API-Football plan publishes `x-ratelimit-limit: 10` (requests
    # per minute). Paginated ingestion waits between pages by default; set to
    # 0 only for a plan that explicitly allows faster bursts.
    api_football_page_delay_seconds: float = 6.1
    # Safety valve, not a completeness assumption: a run never follows more
    # than this many pages even if the provider claims more exist.
    api_football_max_pages_per_run: int = 200
    football_data_token: str | None = None
    football_data_base_url: str = "https://api.football-data.org/v4"

    # --- Database expansion (Phase 1) ---
    # The expansion runner reads the provider's own request budget (GET /status);
    # these are the local safety valves, not a substitute for it.
    ingestion_request_interval_seconds: float = 6.5
    ingestion_max_requests_per_run: int = 0  # 0 = no local cap (the provider budget still applies)
    ingestion_plan_page_cap: int = 3  # the API-Football Free plan caps `page` at 3
    ingestion_priority_leagues_path: str = "data/registry/priority_leagues.json"
    ingestion_country_snapshot_path: str = "data/registry/country_priority_snapshot_2026-10-07.json"
    # Supplementary providers, registered but disabled until a key is supplied.
    openligadb_base_url: str = "https://api.openligadb.de/"
    thesportsdb_base_url: str = "https://www.thesportsdb.com/api.php"
    thesportsdb_key: str | None = None

    # --- Canonical API pagination ---
    # The UI is page-driven; these bounds stop a client from asking for the
    # whole table while keeping the legacy list endpoint bounded as well.
    players_default_page_size: int = 25
    players_max_page_size: int = 100

    # --- StatsBomb Open Data ---
    # Free, no key, CC BY-NC-SA 4.0 — used for event analytics / role-discovery validation,
    # not as a primary fixture/lineup source. Attribution: https://github.com/statsbomb/open-data
    statsbomb_enabled: bool = True
    statsbomb_mode: str = "open_data"
    statsbomb_open_data_repository: str = "https://github.com/hudl/open-data"
    statsbomb_open_data_branch: str = "master"
    statsbomb_local_data_dir: str = "data/bronze/statsbomb-open-data"

    # --- Authentication (handoff §7.8). No default secret and no dev bypass: when
    # AUTH_JWT_SECRET is unset (or < 32 bytes) protected routes answer 503, never "open".
    auth_jwt_secret: str | None = None
    auth_jwt_secret_previous: str | None = None  # accepted during key rotation only
    auth_jwt_issuer: str = "football-os-identity"
    auth_jwt_audience: str = "football-os-api"

    # --- CORS: explicit comma-separated origins only; "*" is rejected at startup (R17).
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"

    # --- LLM Provider Configuration ---
    # Active LLM provider: "groq" | "huggingface" | "openai" | "anthropic" | "gemini" | "none"
    llm_provider: Literal["groq", "huggingface", "openai", "anthropic", "gemini", "none"] = "none"
    # Explicit model ID for the active provider
    llm_model: str | None = None
    # Optional fallback provider
    llm_fallback_provider: Literal["groq", "huggingface", "openai", "anthropic", "gemini", "none"] = "none"
    llm_fallback_model: str | None = None
    # Runtime controls
    llm_allow_paid_fallback: bool = False
    llm_allow_local_fallback: bool = False
    llm_timeout_seconds: int = 45
    llm_max_retries: int = 2
    llm_max_output_tokens: int = 1200
    llm_enable_streaming: bool = True
    # --- Grounded assistant budgets ---
    # The provider's per-minute token budget is the binding constraint on how many
    # tool schemas a request can carry, so the number of tools offered to the model
    # and the number of tool calls per turn are configurable.
    llm_max_tool_schemas: int = 10
    llm_max_tool_calls: int = 8
    llm_max_tool_rounds: int = 4
    llm_tool_timeout_seconds: float = 20.0
    llm_context_budget_chars: int = 6000

    # --- Provider-specific credentials ---
    # Groq (OpenAI-compatible API)
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Hugging Face Inference Providers (OpenAI-compatible)
    hf_token: str | None = None
    hf_base_url: str = "https://router.huggingface.co/v1"

    # OpenAI / OpenAI-compatible
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    # Anthropic
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com/v1"

    # Google Gemini
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"


@lru_cache
def get_settings() -> Settings:
    return Settings()
