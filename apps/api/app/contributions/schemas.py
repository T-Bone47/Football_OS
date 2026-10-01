"""Pydantic schemas for Player Contribution Engine (Phase 3.1)."""
from __future__ import annotations

import datetime
import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict


class ContributionDimensionItem(BaseModel):
    dimension: str
    score: float | None = None
    percentile: float | None = None
    key_metrics: dict[str, float | None]
    confidence: str
    summary: str = ""


class PlayerContributionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_id: uuid.UUID
    player_name: str
    as_of: datetime.datetime
    position_group: str
    sample_minutes: int
    sample_matches: int
    confidence: str  # HIGH, MEDIUM, LOW, INSUFFICIENT_SAMPLE, INSUFFICIENT_DATA
    contribution_status: str  # EVALUATED, INSUFFICIENT_SAMPLE, INSUFFICIENT_DATA
    dimensions: dict[str, ContributionDimensionItem]
    raw_metrics: dict[str, Any]
    strengths: list[str]
    weaknesses: list[str]
    calculation_version: str
    provenance: dict[str, Any]
