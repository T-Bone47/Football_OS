"""Canonical coverage API (Phase 7).

These endpoints expose the measured coverage of the canonical database: counts with
their denominators, per-provider and per-competition status, country-priority
coverage, ingestion checkpoints and the next recommended ingestion tasks.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.coverage.service import (
    competition_coverage,
    compute_coverage,
    country_coverage,
    duplicate_state,
    entity_provenance,
    ingestion_state,
    next_recommended_tasks,
    profile_completeness,
    provider_coverage,
    provenance_summary,
    statistic_completeness,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/coverage", tags=["coverage"])


@router.get("/summary")
async def coverage_summary(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """The full measured coverage view."""
    return await compute_coverage(session)


@router.get("/providers")
async def coverage_providers(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Per-provider identity counts, last success and checkpoint status."""
    return {"providers": await provider_coverage(session)}


@router.get("/competitions")
async def coverage_competitions(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Per competition-season player coverage."""
    return {"competitions": await competition_coverage(session)}


@router.get("/countries")
async def coverage_countries(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Priority-country coverage, with the ranking snapshot that defines the selection."""
    return await country_coverage(session)


@router.get("/ingestion")
async def coverage_ingestion(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Ingestion state: recent runs, checkpoints, failures and the next tasks."""
    return {
        **(await ingestion_state(session)),
        "next_recommended_tasks": await next_recommended_tasks(session),
    }


@router.get("/provenance")
async def coverage_provenance(
    entity_type: str = Query(default="player", max_length=32),
    entity_id: str = Query(default="", max_length=64),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Field-level provenance for one entity, or the provenance summary."""
    if entity_id:
        return await entity_provenance(session, entity_type, entity_id)
    return await provenance_summary(session)


@router.get("/data-quality")
async def coverage_data_quality(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Profile and statistic completeness, plus the duplicate/unresolved state."""
    return {
        "profile_completeness": await profile_completeness(session),
        "statistic_completeness": await statistic_completeness(session),
        "duplicates": await duplicate_state(session),
    }
