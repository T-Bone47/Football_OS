"""Pydantic schemas for the Player Intelligence Engine API (Phase 3.2N)."""
from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class PlayerIntelligenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_id: uuid.UUID
    player_name: str
    position_group: str
    as_of: datetime
    calculation_version: str

    data_status: str
    sample_minutes: int
    sample_matches: int
    confidence: str

    contribution_vector: dict[str, Any]
    intelligence_vector: dict[str, Any]
    peer_benchmarks: dict[str, Any]
    contextual_adjustments: dict[str, Any]
    explanations: dict[str, list[str]]
    trajectory: list[dict[str, Any]]
    provenance: dict[str, Any]


class PlayerTrajectoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_id: uuid.UUID
    player_name: str
    trajectory_status: str
    total_recorded_matches: int
    cumulative_minutes: int
    volatility_score: float | None = None
    timeline: list[dict[str, Any]]
    seasonal_trend: list[dict[str, Any]]


class BenchmarkMetricItem(BaseModel):
    metric: str
    value_p90: float | None = None
    peer_mean: float
    peer_std: float
    z_score: float | None = None
    percentile: float | None = None
    status: str


class PlayerBenchmarksResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_id: uuid.UUID
    player_name: str
    position_group: str
    benchmark_status: str
    sample_minutes: int
    peer_sample_size: int
    average_percentile: float | None = None
    metrics: dict[str, BenchmarkMetricItem]
