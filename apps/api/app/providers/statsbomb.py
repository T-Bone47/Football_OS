"""StatsBomb open data adapter (architecture doc §9). Free, no key, CC BY-NC-SA
4.0 — used for event analytics / role-discovery validation, not as a primary
fixture/lineup source. Attribution: https://github.com/statsbomb/open-data
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.providers.base import RawResponse

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
        response = await self._client.get(url)
        response.raise_for_status()
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
