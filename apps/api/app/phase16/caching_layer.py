from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Set
from pydantic import BaseModel, Field



class CacheEntry(BaseModel):
    cache_key: str
    input_digest: str
    calculation_version: str
    cached_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str
    dependency_entity_ids: list[str] = Field(default_factory=list)
    payload: Any


class DeterministicCache:
    """Safe, deterministic in-memory cache layer with dependency awareness."""

    def __init__(self) -> None:
        self._cache: dict[str, CacheEntry] = {}

    def build_cache_key(self, namespace: str, inputs: dict[str, Any], calculation_version: str) -> tuple[str, str]:
        canonical_input = json.dumps(inputs, sort_keys=True)
        input_digest = hashlib.sha256(canonical_input.encode("utf-8")).hexdigest()
        key = f"{namespace}:{calculation_version}:{input_digest}"
        return key, input_digest

    def set(
        self,
        namespace: str,
        inputs: dict[str, Any],
        calculation_version: str,
        payload: Any,
        ttl_seconds: int = 3600,
        dependency_entity_ids: list[str] | None = None,
    ) -> CacheEntry:
        key, input_digest = self.build_cache_key(namespace, inputs, calculation_version)
        now = datetime.now(timezone.utc)
        exp_dt = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc)

        entry = CacheEntry(
            cache_key=key,
            input_digest=input_digest,
            calculation_version=calculation_version,
            expires_at=exp_dt.isoformat(),
            dependency_entity_ids=dependency_entity_ids or [],
            payload=payload,
        )
        self._cache[key] = entry
        return entry

    def get(
        self,
        namespace: str,
        inputs: dict[str, Any],
        calculation_version: str,
        stale_dependency_ids: set[str] | None = None,
    ) -> Any | None:
        key, _ = self.build_cache_key(namespace, inputs, calculation_version)
        entry = self._cache.get(key)
        if not entry:
            return None

        # Check expiration
        now = datetime.now(timezone.utc)
        exp_dt = datetime.fromisoformat(entry.expires_at)
        if now > exp_dt:
            del self._cache[key]
            return None

        # Check dependency freshness invalidation
        if stale_dependency_ids:
            for dep in entry.dependency_entity_ids:
                if dep in stale_dependency_ids:
                    del self._cache[key]
                    return None

        return entry.payload

    def invalidate(self, cache_key: str) -> bool:
        if cache_key in self._cache:
            del self._cache[cache_key]
            return True
        return False

    def clear(self) -> None:
        self._cache.clear()


_GLOBAL_CACHE: DeterministicCache | None = None


def get_deterministic_cache() -> DeterministicCache:
    global _GLOBAL_CACHE
    if _GLOBAL_CACHE is None:
        _GLOBAL_CACHE = DeterministicCache()
    return _GLOBAL_CACHE
