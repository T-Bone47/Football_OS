"""Provider-specific envelope schemas (architecture doc §26) — not one
universal DTO. These validate the shape of the raw JSON envelope only
(pagination/errors/results-count), not the domain content inside it; that's
Phase 1's canonical-model job. Built from what the architecture doc's own
§7/§8 already say these providers return, not fabricated against a live
response we don't have (api-football/football-data-org aren't reachable
from this sandbox — see docs/DEVELOPMENT_STATUS.md).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiFootballEnvelope(BaseModel):
    get: str
    parameters: dict[str, Any] = {}
    errors: list[Any] = []
    results: int
    paging: dict[str, Any] = {}
    response: list[Any]


class FootballDataOrgEnvelope(BaseModel):
    # football-data.org doesn't wrap in "response"/"results" the way
    # API-Football does; different providers, different envelope shapes —
    # this is exactly why §26 says provider-specific DTOs, not one universal one.
    count: int | None = None
    filters: dict[str, Any] = {}
    competitions: list[Any] | None = None
    matches: list[Any] | None = None
    teams: list[Any] | None = None
