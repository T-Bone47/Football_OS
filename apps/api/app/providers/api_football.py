"""API-Football adapter (architecture doc §7). Requires API_FOOTBALL_KEY.

NOT live-verified in this environment: v3.football.api-sports.io is outside
this sandbox's network allowlist, and no key is configured. Auth-header
wiring and error handling are unit-tested against a mocked transport
(tests/unit/test_provider_protocol.py). Live behaviour must be confirmed
against a real key before this is trusted for Phase 1 ingestion.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.providers.base import RawResponse

_BASE_URL = "https://v3.football.api-sports.io"


class ApiFootballProvider:
    name = "api-football"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        if client is None:
            settings = get_settings()
            if not settings.api_football_key:
                raise RuntimeError("API_FOOTBALL_KEY is not configured")
            client = httpx.AsyncClient(
                base_url=_BASE_URL,
                headers={"x-apisports-key": settings.api_football_key},
                timeout=30.0,
            )
            self._owns_client = True
        else:
            self._owns_client = False
        self._client = client

    async def fetch(self, resource: str, **params: Any) -> RawResponse:
        response = await self._client.get(f"/{resource}", params=params)
        response.raise_for_status()
        return RawResponse(
            content=response.content,
            content_type=response.headers.get("content-type", "application/json"),
            source_url=str(response.url),
            retrieved_at=datetime.now(timezone.utc),
            status_code=response.status_code,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
