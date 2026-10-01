"""Environment separation (§2).

Four explicit environments. Production is never a default: an unknown or
missing ENVIRONMENT value resolves to DEVELOPMENT, and PRODUCTION/STAGING
must be named. `audit_environment()` checks one environment's settings;
`audit_isolation()` checks that several environments share no database,
cache, object storage, artifact directory or secret.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from app.config import Settings


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


_ALIASES = {"dev": "development", "prod": "production", "stage": "staging"}

# Values that ship in .env.example / docker-compose.yml. They are fine on a
# laptop and never acceptable where real data or real users exist.
DEV_DEFAULT_SECRETS = frozenset({"fios", "fios12345", "changeme", "password", "secret", ""})


class EnvironmentConfigError(RuntimeError):
    """Raised at startup when a staging/production config is unsafe."""


def resolve_environment(raw: str | None) -> Environment:
    value = (raw or "development").strip().lower()
    value = _ALIASES.get(value, value)
    try:
        return Environment(value)
    except ValueError as exc:
        raise EnvironmentConfigError(
            f"ENVIRONMENT={raw!r} is not one of {[e.value for e in Environment]}"
        ) from exc


def is_hardened(env: Environment) -> bool:
    return env in (Environment.STAGING, Environment.PRODUCTION)


@dataclass
class EnvironmentAudit:
    environment: Environment
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict:
        return {
            "environment": self.environment.value,
            "ok": self.ok,
            "violations": self.violations,
            "warnings": self.warnings,
        }


def _db_password(url: str) -> str:
    parsed = urlparse(url.replace("+asyncpg", ""))
    return parsed.password or ""


def _cors_origins(settings: Settings) -> list[str]:
    return [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]


def audit_environment(settings: Settings) -> EnvironmentAudit:
    env = resolve_environment(settings.environment)
    audit = EnvironmentAudit(environment=env)
    hardened = is_hardened(env)

    db_pw = _db_password(settings.database_url)
    if db_pw in DEV_DEFAULT_SECRETS:
        (audit.violations if hardened else audit.warnings).append(
            "DATABASE_URL uses a development default password"
        )

    origins = _cors_origins(settings)
    if "*" in origins:
        (audit.violations if hardened else audit.warnings).append(
            "CORS_ALLOWED_ORIGINS contains '*' while credentials are allowed"
        )
    if hardened and any("localhost" in o or "127.0.0.1" in o for o in origins):
        audit.violations.append("CORS_ALLOWED_ORIGINS contains a localhost origin")

    if getattr(settings, "dev_seed", False):
        (audit.violations if hardened else audit.warnings).append(
            "DEV_SEED=true: legacy engines serve demo fixtures, not observed data"
        )

    if hardened:
        if settings.snapshot_storage_backend != "s3":
            audit.violations.append(
                "SNAPSHOT_STORAGE_BACKEND must be 's3' (local filesystem is not durable)"
            )
        elif (settings.s3_secret_key or "") in DEV_DEFAULT_SECRETS:
            audit.violations.append("S3_SECRET_KEY is a development default")
        bucket = settings.s3_bucket or ""
        if bucket and env.value not in bucket:
            audit.warnings.append(
                f"S3_BUCKET '{bucket}' does not name the environment; isolation relies on credentials alone"
            )
        if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
            audit.warnings.append("DATABASE_URL points at localhost")

    return audit


def _redis_identity(url: str) -> str:
    parsed = urlparse(url)
    db = (parsed.path or "/0").lstrip("/") or "0"
    return f"{parsed.hostname}:{parsed.port or 6379}/{db}"


def _db_identity(url: str) -> str:
    parsed = urlparse(url.replace("+asyncpg", ""))
    return f"{parsed.hostname}:{parsed.port or 5432}/{(parsed.path or '').lstrip('/')}"


def _storage_identity(s: Settings) -> str:
    if s.snapshot_storage_backend == "s3":
        return f"s3://{s.s3_endpoint or 'aws'}/{s.s3_bucket}"
    return f"file://{s.snapshot_storage_path}"


def audit_isolation(configs: dict[Environment, Settings]) -> list[str]:
    """Returns every resource shared between two environments."""
    violations: list[str] = []
    resources = {
        "database": lambda s: _db_identity(s.database_url),
        "redis": lambda s: _redis_identity(s.redis_url),
        "object_storage": _storage_identity,
        "model_artifacts": lambda s: s.model_artifact_dir,
    }
    envs = list(configs.items())
    for name, ident in resources.items():
        seen: dict[str, Environment] = {}
        for env, s in envs:
            key = ident(s)
            if key in seen:
                violations.append(f"{name} shared by {seen[key].value} and {env.value}: {key}")
            else:
                seen[key] = env

    secret_fields = ("api_football_key", "football_data_token", "s3_secret_key")
    for f in secret_fields:
        seen_secret: dict[str, Environment] = {}
        for env, s in envs:
            value = getattr(s, f) or ""
            if not value or value in DEV_DEFAULT_SECRETS:
                continue
            if value in seen_secret:
                violations.append(f"secret {f.upper()} shared by {seen_secret[value].value} and {env.value}")
            else:
                seen_secret[value] = env
    return violations


def enforce_startup_policy(settings: Settings) -> EnvironmentAudit:
    """Called from app startup. Hardened environments refuse to boot unsafe."""
    audit = audit_environment(settings)
    if is_hardened(audit.environment) and not audit.ok:
        raise EnvironmentConfigError(
            f"{audit.environment.value} configuration rejected: " + "; ".join(audit.violations)
        )
    return audit
