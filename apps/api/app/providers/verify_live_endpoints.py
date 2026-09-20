"""One-time, sequential, rate-limit-safe live verification of specific
API-Football endpoints ("API-FOOTBALL LIVE ENDPOINT VERIFICATION" phase).

Routes through the existing IngestionService — which already calls
ApiFootballProvider.fetch() internally and gives provenance, validation,
and CapabilityRegistry.mark_verified() on real success for free. This
script sequences and classifies that, it does not duplicate it.

Run as: python -m app.providers.verify_live_endpoints
(needs the real app DB configured, not the test DB)

Must run somewhere with real network access to v3.football.api-sports.io.
Running it anywhere that lacks that reports NOT RUN for every endpoint,
honestly — this script cannot produce a fabricated SUCCESS.

Rules enforced here, not just documented:
- exactly one request per endpoint, sequential, never parallel
- stops immediately after AUTHORIZATION FAILURE or QUOTA FAILURE — does
  not go on to try the next endpoint (§8)
- CapabilityRegistry.mark_verified() only fires when IngestionService
  itself reported SUCCESS on a real request — never on "looks implemented"
- never prints the API key (only non-secret params/results are logged)
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db.models.provenance import DataSnapshot
from app.db.session import async_session
from app.ingestion.capability_registry import CapabilityRegistry
from app.ingestion.service import IngestionService
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.providers.api_football import ApiFootballProvider
from app.providers.registry import ProviderRegistry

# Reasonable, publicly-documented minimal queries (league 39 = Premier
# League, a stable well-known ID on this API) — NOT verified against your
# specific plan/coverage. Override the params below if your plan differs.
_SEASON = 2026
ENDPOINTS: list[tuple[str, dict]] = [
    ("leagues", {"current": "true"}),
    ("teams", {"league": 39, "season": _SEASON}),
    ("players", {"league": 39, "season": _SEASON, "page": 1}),
    ("fixtures", {"league": 39, "season": _SEASON, "next": 1}),
]


@dataclass
class EndpointVerification:
    endpoint: str
    params: dict
    outcome: str = "NOT RUN"
    detail: str = ""
    http_status: int | None = None
    results: int | None = None
    paging: dict | None = None
    capability_marked_verified: bool = False


def classify(status_value: str, error: str | None) -> tuple[str, str]:
    if status_value == "SUCCESS":
        return "SUCCESS", "genuine successful live response"
    error = error or ""
    if "ProviderRateLimitError" in error:
        return "QUOTA FAILURE", error
    if "ProviderAuthorizationError" in error or "ProviderAuthenticationError" in error:
        return "AUTHORIZATION FAILURE", error
    if "ProviderBadRequestError" in error:
        return "API-LEVEL FAILURE", error
    if "ProviderUnavailableError" in error:
        return "NOT RUN", error
    if "does not support resource" in error:
        return "ENDPOINT/COVERAGE LIMITATION", error
    return "ERROR", error


async def _read_envelope(session, run) -> dict | None:
    """Best-effort only: works for the local snapshot backend by reading the
    file directly; returns None (not an error) for the s3:// backend or any
    read/parse failure — the outcome classification above doesn't depend on
    this succeeding, it's extra detail when available."""
    snapshot = (
        await session.execute(select(DataSnapshot).where(DataSnapshot.ingestion_run_id == run.id))
    ).scalar_one_or_none()
    if snapshot is None or snapshot.storage_location.startswith("s3://"):
        return None
    try:
        return json.loads(Path(snapshot.storage_location).read_bytes())
    except Exception:
        return None


async def run_verification() -> list[EndpointVerification]:
    settings = get_settings()
    if not settings.api_football_key:
        return [
            EndpointVerification(endpoint=e, params=p, outcome="NOT RUN", detail="API_FOOTBALL_KEY not configured")
            for e, p in ENDPOINTS
        ]

    registry = ProviderRegistry()
    registry.register("api-football", ApiFootballProvider)
    store = LocalFilesystemSnapshotStore(settings.snapshot_storage_path)

    results: list[EndpointVerification] = []
    async with async_session() as session:
        capabilities = CapabilityRegistry(session)
        service = IngestionService(
            session=session, provider_registry=registry, snapshot_store=store, capability_registry=capabilities
        )

        for endpoint, params in ENDPOINTS:
            run = await service.run("api-football", endpoint, **params)
            status_value = run.status.value if hasattr(run.status, "value") else run.status
            outcome, detail = classify(status_value, run.error)

            result = EndpointVerification(endpoint=endpoint, params=params, outcome=outcome, detail=detail)
            if outcome == "SUCCESS":
                result.capability_marked_verified = True  # IngestionService already called mark_verified
                envelope = await _read_envelope(session, run)
                if envelope is not None:
                    result.results = envelope.get("results")
                    result.paging = envelope.get("paging")
            results.append(result)

            if outcome in ("QUOTA FAILURE", "AUTHORIZATION FAILURE"):
                break  # §8: stop immediately, do not go on to the next endpoint

    return results


def print_report(results: list[EndpointVerification]) -> None:
    print("API-FOOTBALL LIVE ENDPOINT VERIFICATION")
    print("=" * 40)
    for r in results:
        print()
        print(f"/{r.endpoint}  params={r.params}")
        print(f"Outcome: {r.outcome}")
        print(f"Results: {r.results if r.results is not None else 'n/a'}")
        print(f"Capability marked verified: {r.capability_marked_verified}")
        print(f"Detail: {r.detail}")


if __name__ == "__main__":
    _results = asyncio.run(run_verification())
    print_report(_results)
