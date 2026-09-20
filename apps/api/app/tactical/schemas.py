"""Pydantic schemas for Tactical Fit Engine APIs (Phase 2 Slice 3)."""
from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class TacticalRequirementSchema(BaseModel):
    dimension: str
    required_strength: float
    importance_weight: float
    minimum_threshold: float | None = None
    description: str = ""


class TacticalContextResponse(BaseModel):
    context_id: str
    formation: str
    target_position: str
    position_group: str
    target_role: str
    requirements: list[TacticalRequirementSchema]
    possession_style: str | None = None
    pressing_style: str | None = None
    build_up_style: str | None = None
    transition_style: str | None = None
    version: str
    description: str = ""


class DimensionFitItem(BaseModel):
    player_score: float
    required_strength: float
    fit_score: float
    importance_weight: float
    minimum_threshold: float | None = None
    deficit: float = 0.0


class PlayerTacticalFitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    player_id: uuid.UUID
    player_name: str
    team_id: uuid.UUID | None = None
    season_id: uuid.UUID | None = None
    tactical_context_id: str
    formation: str
    target_position: str
    position_group: str
    target_role: str
    fit_score: float
    position_fit: float
    role_fit: float
    dimension_fit: float
    style_fit: float | None = None
    contextual_fit: float | None = None
    confidence: str  # 'HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT_DATA'
    fit_status: str  # 'FIT', 'MODERATE_FIT', 'POOR_FIT', 'INSUFFICIENT_DATA'
    dimension_breakdown: dict[str, Any]
    why_fit: list[str]
    why_not_fit: list[str]
    calculation_version: str
    feature_set_version: str
    as_of: datetime
    provenance: dict[str, Any]
    created_at: datetime


class TacticalFitComparisonRequest(BaseModel):
    player_a_id: uuid.UUID
    player_b_id: uuid.UUID
    context_id: str | None = None
    formation: str | None = None
    target_position: str | None = None
    target_role: str | None = None
    as_of: datetime | None = None


class TacticalFitComparisonResponse(BaseModel):
    context_id: str
    formation: str
    target_position: str
    target_role: str
    player_a: PlayerTacticalFitResponse
    player_b: PlayerTacticalFitResponse
    comparison_summary: str
    dimensional_deltas: dict[str, dict[str, float]]
