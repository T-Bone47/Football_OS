"""Pydantic schemas for Role Discovery and Player Similarity APIs (Phase 2 Slice 2)."""
from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class RoleProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    player_id: uuid.UUID
    as_of: datetime
    feature_set_version: str
    role_status: str  # 'QUALIFIED', 'INSUFFICIENT_SAMPLE'
    sample_minutes: int
    sample_matches: int
    position_group: str
    primary_archetype: str | None = None
    secondary_archetype: str | None = None
    archetype_confidence: float | None = None
    profile_scores: dict[str, float]
    feature_vector: dict[str, float]
    provenance: dict[str, Any]
    created_at: datetime


class RoleArchetypeResponse(BaseModel):
    player_id: uuid.UUID
    player_name: str
    role_status: str
    position_group: str
    sample_minutes: int
    sample_matches: int
    primary_archetype: str | None = None
    secondary_archetype: str | None = None
    archetype_confidence: float | None = None
    dominant_dimensions: list[str]
    summary: str


class SimilarPlayerItem(BaseModel):
    player_id: uuid.UUID
    player_name: str
    primary_position: str | None = None
    position_group: str
    sample_minutes: int
    primary_archetype: str | None = None
    overall_similarity: float
    statistical_similarity: float
    role_similarity: float
    contextual_similarity: float
    why_similar: list[str]
    why_different: list[str]


class SimilarPlayersResponse(BaseModel):
    target_player_id: uuid.UUID
    target_player_name: str
    as_of: datetime
    total_evaluated: int
    results: list[SimilarPlayerItem]


class PlayerComparisonResponse(BaseModel):
    player_a_id: uuid.UUID
    player_a_name: str
    player_b_id: uuid.UUID
    player_b_name: str
    overall_similarity: float
    statistical_similarity: float
    role_similarity: float
    contextual_similarity: float
    profile_comparison: dict[str, dict[str, float]]
    why_similar: list[str]
    why_different: list[str]
