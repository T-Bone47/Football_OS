"""Match Prediction & Calibration Engine (Phase 6)."""
from app.prediction.schemas import (
    CalibrationInfo,
    ExpectedGoals,
    FeatureContribution,
    GoalDistribution,
    MatchPredictionHistoryItem,
    MatchPredictionHistoryResponse,
    MatchPredictionResponse,
    ModelStatusResponse,
    OutcomeProbabilities,
    PredictionExplanation,
    ScorelineProbability,
)

from app.prediction.service import MatchPredictionService
from app.prediction.registry import model_registry

__all__ = [
    "CalibrationInfo",
    "ExpectedGoals",
    "FeatureContribution",
    "GoalDistribution",
    "MatchPredictionHistoryItem",
    "MatchPredictionHistoryResponse",
    "MatchPredictionResponse",
    "ModelStatusResponse",
    "OutcomeProbabilities",
    "PredictionExplanation",
    "ScorelineProbability",
    "MatchPredictionService",
    "model_registry",
]

