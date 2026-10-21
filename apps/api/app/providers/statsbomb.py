"""StatsBomb open data adapter (architecture doc §9). Free, no key, CC BY-NC-SA
4.0 — used for event analytics / role-discovery validation, not as a primary
fixture/lineup source. Attribution: https://github.com/statsbomb/open-data
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.providers.base import RawResponse
from app.providers.errors import classify_http_status_error, classify_transport_error
from app.providers.http import request_with_retry_config

_BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

_RESOURCES = {
    "competitions": "/competitions.json",
    "matches": "/matches/{competition_id}/{season_id}.json",
    "events": "/events/{match_id}.json",
    "lineups": "/lineups/{match_id}.json",
}


class StatsBombProvider:
    name = "statsbomb"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def fetch(self, resource: str, **params: Any) -> RawResponse:
        if resource not in _RESOURCES:
            raise ValueError(f"StatsBomb adapter does not support resource '{resource}'")
        url = f"{_BASE_URL}{_RESOURCES[resource].format(**params)}"
        try:
            response = await self._get_with_retry(url)
        except httpx.HTTPStatusError as exc:
            raise classify_http_status_error(exc) from exc
        except httpx.TransportError as exc:
            raise classify_transport_error(exc) from exc
        return self._to_raw_response(response, url)

    @request_with_retry_config(max_attempts=3)
    async def _get_with_retry(self, url: str) -> httpx.Response:
        response = await self._client.get(url)
        response.raise_for_status()
        return response

    def _to_raw_response(self, response: httpx.Response, url: str) -> RawResponse:
        return RawResponse(
            content=response.content,
            content_type=response.headers.get("content-type", "application/json"),
            source_url=url,
            retrieved_at=datetime.now(timezone.utc),
            status_code=response.status_code,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def verify_health(self) -> dict:
        """Verify StatsBomb connectivity."""
        try:
            resp = await self.fetch("competitions")
            if resp.status_code == 200:
                data = resp.content
                try:
                    import json
                    data = json.loads(data)
                    count = len(data) if isinstance(data, list) else 0
                except Exception:
                    count = 0
                return {
                    "status": "AVAILABLE",
                    "provider": self.name,
                    "model": "statsbomb-open-data",
                    "competitions_count": count,
                }
            else:
                return {
                    "status": "DEGRADED",
                    "provider": self.name,
                    "model": "statsbomb-open-data",
                    "error": f"HTTP {resp.status_code}",
                }
        except httpx.TimeoutException:
            return {
                "status": "UNAVAILABLE",
                "provider": self.name,
                "model": "statsbomb-open-data",
                "error": "Timeout",
            }
        except httpx.TransportError as e:
            return {
                "status": "UNAVAILABLE",
                "provider": self.name,
                "model": "statsbomb-open-data",
                "error": f"Network error: {e}",
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "provider": self.name,
                "model": "statsbomb-open-data",
                "error": str(e),
            }
