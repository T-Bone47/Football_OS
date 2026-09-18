"""API-Football adapter (architecture doc §7; connectivity-forensics doc
§1-§21 for the specific decisions below).

Base URL is the direct API-Sports host, not the website
(v3.football.api-sports.io, not api-football.com — doc §1), and it's
configurable rather than hardcoded so a host change is a one-line env edit.
Auth is `x-apisports-key`, not `Authorization: Bearer` (§2).

Verification status: DNS resolves for this host from this sandbox; the
actual HTTP request is rejected by this sandbox's OWN egress proxy before
it reaches api-sports.io at all (`x-deny-reason: host_not_allowed` — a
header this environment's own proxy adds, confirmed identical with and
without a valid key). That is NOT evidence the key or the adapter is wrong;
it means this specific sandbox can't reach the host. See
docs/DEVELOPMENT_STATUS.md and ADR-007. Auth-header wiring, retry policy,
and error classification are unit-tested against a mocked transport
(tests/unit/test_provider_protocol.py, tests/unit/test_provider_errors.py).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.providers.base import RawResponse
from app.providers.errors import ProviderBadRequestError, classify_http_status_error, classify_transport_error
from app.providers.http import request_with_retry_config


class ApiFootballProvider:
    name = "api-football"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        if client is None:
            settings = get_settings()
            if not settings.api_football_key:
                raise RuntimeError("API_FOOTBALL_KEY is not configured")
            client = httpx.AsyncClient(
                base_url=settings.api_football_base_url,
                headers={"x-apisports-key": settings.api_football_key},
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
        self._raise_if_envelope_has_errors(response)
        return self._to_raw_response(response)

    @request_with_retry_config(max_attempts=3)
    async def _get_with_retry(self, resource: str, params: dict) -> httpx.Response:
        response = await self._client.get(f"/{resource}", params=params)
        response.raise_for_status()
        return response

    def _raise_if_envelope_has_errors(self, response: httpx.Response) -> None:
        """§18: HTTP 200 != usable data — API-Football puts request-level
        errors inside the envelope, not the status code."""
        try:
            payload = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return  # not JSON — let downstream validation classify this
        errors = payload.get("errors") if isinstance(payload, dict) else None
        if errors:
            raise ProviderBadRequestError(f"API-Football returned errors in a 200 response: {errors}")

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
