"""football-data.org adapter (architecture doc §8). Requires
FOOTBALL_DATA_ORG_KEY. Same live-verification caveat as api_football.py —
football-data.org is outside this sandbox's network allowlist.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.providers.base import RawResponse
from app.providers.http import request_with_retry_config

_BASE_URL = "https://api.football-data.org/v4"


class FootballDataOrgProvider:
    name = "football-data-org"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        if client is None:
            settings = get_settings()
            if not settings.football_data_org_key:
                raise RuntimeError("FOOTBALL_DATA_ORG_KEY is not configured")
            client = httpx.AsyncClient(
                base_url=_BASE_URL,
                headers={"X-Auth-Token": settings.football_data_org_key},
                timeout=30.0,
            )
            self._owns_client = True
        else:
            self._owns_client = False
        self._client = client

    async def fetch(self, resource: str, **params: Any) -> RawResponse:
        response = await self._get_with_retry(resource, params)
        return self._to_raw_response(response)

    @request_with_retry_config(max_attempts=3)
    async def _get_with_retry(self, resource: str, params: dict) -> httpx.Response:
        response = await self._client.get(f"/{resource}", params=params)
        response.raise_for_status()
        return response

    def _to_raw_response(self, response: httpx.Response) -> RawResponse:
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
