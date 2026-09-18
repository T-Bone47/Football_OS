"""football-data.org adapter (architecture doc §8). Requires
FOOTBALL_DATA_TOKEN. Auth is `X-Auth-Token` (connectivity-forensics doc §14).

Verification status: same as api_football.py — DNS resolves, but this
sandbox's own egress proxy rejects the request before it reaches
api.football-data.org (`x-deny-reason: host_not_allowed`, identical with
and without a valid token). See docs/DEVELOPMENT_STATUS.md and ADR-007.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.providers.base import RawResponse
from app.providers.errors import classify_http_status_error, classify_transport_error
from app.providers.http import request_with_retry_config


class FootballDataOrgProvider:
    name = "football-data-org"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        if client is None:
            settings = get_settings()
            if not settings.football_data_token:
                raise RuntimeError("FOOTBALL_DATA_TOKEN is not configured")
            client = httpx.AsyncClient(
                base_url=settings.football_data_base_url,
                headers={"X-Auth-Token": settings.football_data_token},
                timeout=30.0,
            )
            self._owns_client = True
        else:
            self._owns_client = False
        self._client = client

    async def fetch(self, resource: str, **params: Any) -> RawResponse:
        try:
            response = await self._get_with_retry(resource, params)
        except httpx.HTTPStatusError as exc:
            raise classify_http_status_error(exc) from exc
        except httpx.TransportError as exc:
            raise classify_transport_error(exc) from exc
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
