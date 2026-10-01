"""Pydantic schemas for Match Prediction & Calibration Engine (Phase 6).
Guarantees strict probabilistic constraints (sum to 1 within numerical tolerance),
explainability attribution, and transparent data sufficiency statuses.
"""
from __future__ import annotations

from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class OutcomeProbabilities(BaseModel):
    """1X2 Outcome probabilities strictly normalized to sum to 1.0."""
    model_config = ConfigDict(extra="ignore")

    home_win: float = Field(..., ge=0.0, le=1.0, description="Probability of Home Win")
    draw: float = Field(..., ge=0.0, le=1.0, description="Probability of Draw")
    away_win: float = Field(..., ge=0.0, le=1.0, description="Probability of Away Win")

    @field_validator("away_win")
    @classmethod
    def validate_sum_to_one(cls, v: float, info) -> float:
        data = info.data
        if "home_win" in data and "draw" in data:
            total = data["home_win"] + data["draw"] + v
            if abs(total - 1.0) > 1e-3:
                raise ValueError(f"Probabilities must sum to 1.0 within numerical tolerance (got {total:.5f})")
        return v


class ExpectedGoals(BaseModel):
    """Pre-match expected goals derived from pre-match attack and defense parameters."""
    model_config = ConfigDict(extra="ignore")

    home: float = Field(..., ge=0.0, description="Expected goals for Home team")
    away: float = Field(..., ge=0.0, description="Expected goals for Away team")
    total: float = Field(..., ge=0.0, description="Expected combined total goals")


class ScorelineProbability(BaseModel):
    """Probability of a specific final scoreline."""
    model_config = ConfigDict(extra="ignore")

    score: str  # e.g. "1-0", "2-1", "0-0"
    home_goals: int
    away_goals: int
    probability: float = Field(..., ge=0.0, le=1.0)


class GoalDistribution(BaseModel):
    """Complete goal and scoreline distribution derived from pre-match bivariate model."""
    model_config = ConfigDict(extra="ignore")

    expected_goals: ExpectedGoals
    top_scorelines: list[ScorelineProbability] = Field(default_factory=list)
    over_1_5: float = Field(..., ge=0.0, le=1.0)
    over_2_5: float = Field(..., ge=0.0, le=1.0)
    under_2_5: float = Field(..., ge=0.0, le=1.0)
    both_teams_to_score: float = Field(..., ge=0.0, le=1.0)


class FeatureContribution(BaseModel):
    """Explainability factor detailing how an individual feature contributed to the prediction."""
    model_config = ConfigDict(extra="ignore")

    feature_name: str
    value: float | None = None
    contribution: float = 0.0  # Positive favors home, negative favors away
    direction: str = "NEUTRAL"  # FAVORS_HOME, FAVORS_AWAY, NEUTRAL
    description: str


class PredictionExplanation(BaseModel):
    """Explainable summary of pre-match predictive drivers."""
    model_config = ConfigDict(extra="ignore")

    summary: str
    key_factors: list[FeatureContribution] = Field(default_factory=list)
    home_strengths: list[str] = Field(default_factory=list)
    away_strengths: list[str] = Field(default_factory=list)
    context_notes: list[str] = Field(default_factory=list)


class CalibrationInfo(BaseModel):
    """Calibration metadata and empirical quality diagnostics."""
    model_config = ConfigDict(extra="ignore")

    status: str = "CALIBRATED"  # CALIBRATED, RAW, EMPIRICAL_BASELINES
    method: str = "TEMPERATURE_SCALING"  # TEMPERATURE_SCALING, PLATT_SCALING, ISOTONIC, NONE
    brier_score: float | None = None
    expected_calibration_error: float | None = None


class MatchPredictionResponse(BaseModel):
    """Complete, leakage-safe match intelligence prediction contract."""
    model_config = ConfigDict(extra="ignore")

    match_id: uuid.UUID
    as_of: datetime
    home_club_id: uuid.UUID
    home_club_name: str
    away_club_id: uuid.UUID
    away_club_name: str
    probabilities: OutcomeProbabilities
    expected_goals: ExpectedGoals
    goal_distribution: GoalDistribution
    calibration: CalibrationInfo
    model_version: str
    feature_version: str
    data_status: str  # PREDICTION_AVAILABLE, LOW_CONFIDENCE, INSUFFICIENT_DATA, OUT_OF_DISTRIBUTION
    data_sufficiency_reasons: list[str] = Field(default_factory=list)
    explanation: PredictionExplanation
    evaluated_at: datetime


class MatchPredictionHistoryItem(BaseModel):
    """Point-in-time snapshot of prediction evolution over timeline."""
    model_config = ConfigDict(extra="ignore")

    prediction_time: datetime
    as_of: datetime
    probabilities: OutcomeProbabilities
    expected_goals: ExpectedGoals
    model_version: str
    data_status: str


class MatchPredictionHistoryResponse(BaseModel):
    """Audit log of historical predictions generated for a match."""
    model_config = ConfigDict(extra="ignore")

    match_id: uuid.UUID
    history: list[MatchPredictionHistoryItem] = Field(default_factory=list)


class ModelStatusResponse(BaseModel):
    """Operational status and verified backtest performance of the active match prediction model."""
    model_config = ConfigDict(extra="ignore")

    active_model_id: str
    model_version: str
    feature_version: str
    algorithm: str
    training_matches_count: int
    validation_matches_count: int
    log_loss: float
    brier_score: float
    accuracy: float
    macro_f1: float
    expected_calibration_error: float
    calibration_method: str
    status: str  # MODEL_VALIDATED, MODEL_CANDIDATE, PREDICTION_FOUNDATION_COMPLETE
    temporal_validation_passed: bool
    leakage_tests_passed: bool
    registered_at: datetime
