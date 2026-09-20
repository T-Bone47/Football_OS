"""Pydantic schemas for Feature Engineering (Phase 2 Slice 1)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FeatureDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    feature_set: str
    entity_type: str
    version: str
    dtype: str
    description: str
    required_inputs: list[str]
    leakage_policy: str
    window: str | None = None
    nullable: bool
    source: str


class FeatureSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    match_id: uuid.UUID | None = None
    feature_set: str
    calculation_version: str
    as_of: datetime
    season_id: uuid.UUID | None = None
    competition_id: uuid.UUID | None = None
    features: dict[str, Any]
    provenance: dict[str, Any]
    created_at: datetime


class MatchContextFeaturesResponse(BaseModel):
    match_id: uuid.UUID
    as_of: datetime
    home_club_id: uuid.UUID
    away_club_id: uuid.UUID
    home_features: dict[str, Any]
    away_features: dict[str, Any]
    match_context: dict[str, Any]
    provenance: dict[str, Any]
