"""Pydantic schemas for Market Intelligence, Transfers, and Valuation (Phase 4.1).
"""
from __future__ import annotations

from datetime import date, datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NormalizedTransfer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str
    source_record_id: str | None
    provider_player_id: str
    player_name: str
    from_provider_club_id: str | None = None
    from_club_name: str | None = None
    to_provider_club_id: str | None = None
    to_club_name: str | None = None
    transfer_date: date | None = None
    transfer_type: str = "PERMANENT"
    fee_value: float | None = None
    fee_currency: str | None = None
    fee_status: str = "UNKNOWN_FEE"
    fee_eur_normalized: float | None = None
    is_loan: bool = False
    is_permanent: bool = True
    option_type: str = "NONE"
    raw_data: dict[str, Any] = Field(default_factory=dict)


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    player_id: uuid.UUID
    player_name: str | None = None
    from_club_id: uuid.UUID | None = None
    from_club_name: str | None = None
    to_club_id: uuid.UUID | None = None
    to_club_name: str | None = None
    transfer_date: date | None = None
    season_id: uuid.UUID | None = None
    competition_context: str | None = None
    transfer_type: str
    fee_value: float | None = None
    fee_currency: str | None = None
    fee_status: str
    fee_eur_normalized: float | None = None
    is_loan: bool
    is_permanent: bool
    option_type: str
    source_provider: str
    source_record_id: str | None = None
    data_quality_status: str
    quality_reasons: list[str] = Field(default_factory=list)
    created_at: datetime


class MarketContextResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    player_id: uuid.UUID
    as_of: datetime
    age_at_as_of: float | None = None
    position_group: str | None = None
    primary_position: str | None = None
    current_club_id: uuid.UUID | None = None
    current_club_name: str | None = None
    role_archetype: str | None = None
    contribution_scores: dict[str, float] = Field(default_factory=dict)
    sample_minutes: int = 0
    sample_matches: int = 0
    total_career_transfers: int = 0
    last_transfer_date: date | None = None
    last_transfer_fee_eur: float | None = None
    last_fee_status: str | None = None


class ComparableTransferItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    transfer_id: uuid.UUID
    player_id: uuid.UUID
    player_name: str
    from_club_name: str | None = None
    to_club_name: str | None = None
    transfer_date: date | None = None
    transfer_type: str
    fee_value: float | None = None
    fee_currency: str | None = None
    fee_eur_normalized: float | None = None
    fee_status: str
    player_age_at_transfer: float | None = None
    position_group: str
    role_archetype: str | None = None
    similarity_score: float
    similarity_breakdown: dict[str, float] = Field(default_factory=dict)


class ComparableTransfersResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    target_player_id: uuid.UUID
    target_player_name: str
    as_of: datetime
    comparables_count: int
    comparables: list[ComparableTransferItem] = Field(default_factory=list)
    calculation_version: str = "comparable_v1"


class MarketBenchmarkResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    position_group: str
    time_window: str
    sample_size: int
    data_status: str  # 'EVALUATED', 'INSUFFICIENT_DATA'
    median_fee_eur: float | None = None
    q1_fee_eur: float | None = None
    q3_fee_eur: float | None = None
    iqr_fee_eur: float | None = None
    min_fee_eur: float | None = None
    max_fee_eur: float | None = None
    population_definition: str
    calculation_version: str = "market_benchmark_v1"


class ValuationBaselineResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    player_id: uuid.UUID
    player_name: str
    as_of: datetime
    valuation_status: str  # 'VALUATION_AVAILABLE', 'VALUATION_UNAVAILABLE'
    range_status: str      # 'RANGE_AVAILABLE', 'RANGE_NOT_AVAILABLE'
    confidence: str        # 'HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT_DATA'
    estimated_value_eur: float | None = None
    lower_bound_eur: float | None = None
    upper_bound_eur: float | None = None
    comparable_sample_size: int = 0
    cohort_median_fee_eur: float | None = None
    adjustments: dict[str, Any] = Field(default_factory=dict)
    methodology: str
    calculation_version: str = "valuation_baseline_v1"


class MarketCoverageResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_transfers: int
    known_fees_count: int
    reported_fees_count: int
    unknown_fees_count: int
    free_transfers_count: int
    loans_count: int
    qualified_transfers_count: int
    unique_players_count: int
    unique_clubs_count: int
    earliest_transfer_date: date | None = None
    latest_transfer_date: date | None = None
    fee_coverage_pct: float
    readiness_status: str  # 'READY_FOR_VALUATION_MODEL', 'INSUFFICIENT_TRANSFER_DATA'
    limitations: list[str] = Field(default_factory=list)


class ValuationMLPredictionResponse(BaseModel):
    """Production ML valuation point estimate with uncertainty and sufficiency gating (Phase 4.2X)."""
    model_config = ConfigDict(extra="ignore")

    player_id: uuid.UUID
    as_of: datetime
    estimated_value_eur: float
    lower_bound_eur: float
    upper_bound_eur: float
    uncertainty_eur: float
    coverage_level: float = 0.80
    data_status: str
    model_version: str
    feature_version: str
    algorithm: str
    gate_decision: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ValuationMLExplanationResponse(BaseModel):
    """Deterministic SHAP and feature attribution explanation (Phase 4.2X)."""
    model_config = ConfigDict(extra="ignore")

    player_id: uuid.UUID
    as_of: datetime
    model_version: str
    feature_version: str
    method: str
    base_value_log: float
    prediction_log: float
    top_positive_contributors: list[dict[str, Any]] = Field(default_factory=list)
    top_negative_contributors: list[dict[str, Any]] = Field(default_factory=list)


class ValuationMLComparablesResponse(BaseModel):
    """Model estimate alongside historical comparable transfers evidence (Phase 4.2X)."""
    model_config = ConfigDict(extra="ignore")

    player_id: uuid.UUID
    as_of: datetime
    model_estimated_value_eur: float
    comparable_median_fee_eur: float
    comparables: list[dict[str, Any]] = Field(default_factory=list)


class ValuationModelStatusResponse(BaseModel):
    """Operational status and performance lineage of active valuation model (Phase 4.2X)."""
    model_config = ConfigDict(extra="ignore")

    active: bool
    status: str
    model_id: str | None = None
    model_version: str | None = None
    dataset_version: str | None = None
    feature_set_version: str | None = None
    algorithm: str | None = None
    created_at: str | None = None
    test_metrics: dict[str, Any] = Field(default_factory=dict)
    release_gate_checklist: dict[str, bool] = Field(default_factory=dict)
    message: str | None = None
