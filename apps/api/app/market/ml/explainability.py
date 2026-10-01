"""Phase 4.2: Transfer Valuation ML Engine — Model Explainability & Attribution.

Implements deterministic model explanations via SHAP (SHapley Additive exPlanations)
and tree-based feature attributions.

CRITICAL POLICY (Non-Causal Language):
--------------------------------------
Feature attributions describe how the mathematical model assembled its prediction relative
to its baseline. They do NOT represent real-world causal mechanisms.
Every explanation string explicitly uses language such as:
  "contributed positively to the model prediction"
  "contributed negatively to the model prediction"
NEVER:
  "caused the player to be worth €X"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np

from app.market.ml.features import VALUATION_FEATURE_SET_V1, get_valuation_feature_names


# Clean human-readable display names and units for feature explainability
FEATURE_DISPLAY_METADATA: Dict[str, Dict[str, str]] = {
    "age": {"label": "Age at Transfer", "unit": "years"},
    "is_goalkeeper": {"label": "Goalkeeper Indicator", "unit": "binary"},
    "is_defender": {"label": "Defender Indicator", "unit": "binary"},
    "is_midfielder": {"label": "Midfielder Indicator", "unit": "binary"},
    "is_attacker": {"label": "Attacker Indicator", "unit": "binary"},
    "minutes_played_season": {"label": "Minutes Played (Prior 365d)", "unit": "minutes"},
    "appearances_season": {"label": "Appearances (Prior 365d)", "unit": "matches"},
    "goals_per90": {"label": "Goals per 90", "unit": "rate"},
    "assists_per90": {"label": "Assists per 90", "unit": "rate"},
    "goal_involvement_per90": {"label": "Goal Involvement per 90", "unit": "rate"},
    "player_rating_mean": {"label": "Mean Match Rating", "unit": "rating [0-10]"},
    "progression_contribution": {"label": "Progression Contribution", "unit": "score [0-1]"},
    "creation_contribution": {"label": "Creation Contribution", "unit": "score [0-1]"},
    "finishing_contribution": {"label": "Finishing Contribution", "unit": "score [0-1]"},
    "defending_contribution": {"label": "Defending Contribution", "unit": "score [0-1]"},
    "primary_role_confidence": {"label": "Primary Role Confidence", "unit": "probability [0-1]"},
    "performance_trend_slope": {"label": "Performance Trajectory Trend", "unit": "slope"},
    "development_trajectory_score": {"label": "Development Trajectory", "unit": "index"},
    "selling_club_tier": {"label": "Selling Club Competition Tier", "unit": "tier [1-5]"},
    "starter_exposure_rate": {"label": "Starting Lineup Exposure", "unit": "ratio [0-1]"},
    "cohort_median_fee_eur": {"label": "Market Cohort Prior Fee Benchmark", "unit": "EUR"},
    "comparable_median_fee_eur": {"label": "Historical Comparable Median Fee", "unit": "EUR"},
    "prior_transfers_count": {"label": "Historical Transfer Count", "unit": "count"},
}


@dataclass(frozen=True)
class FeatureAttributionItem:
    """Individual feature contribution to a specific valuation prediction."""
    feature_name: str
    display_label: str
    feature_value: float
    unit: str
    attribution_value: float  # impact on model prediction (log-space SHAP)
    direction: str            # POSITIVE or NEGATIVE
    rank: int
    narrative: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "display_label": self.display_label,
            "feature_value": round(self.feature_value, 4),
            "unit": self.unit,
            "attribution_value": round(self.attribution_value, 4),
            "direction": self.direction,
            "rank": self.rank,
            "narrative": self.narrative,
        }


@dataclass
class ValuationExplanation:
    """Deterministic explanation container for a single valuation prediction."""
    player_id: str
    model_version: str
    feature_version: str
    base_value_log: float
    prediction_log: float
    top_positive_contributors: List[FeatureAttributionItem] = field(default_factory=list)
    top_negative_contributors: List[FeatureAttributionItem] = field(default_factory=list)
    method: str = "SHAP"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "base_value_log": round(self.base_value_log, 4),
            "prediction_log": round(self.prediction_log, 4),
            "top_positive_contributors": [item.to_dict() for item in self.top_positive_contributors],
            "top_negative_contributors": [item.to_dict() for item in self.top_negative_contributors],
            "method": self.method,
        }


class ValuationExplainer:
    """Extracts SHAP and feature attribution values for valuation models."""

    def __init__(
        self,
        model: Any,
        feature_names: Optional[List[str]] = None,
        model_version: str = "VALUATION_ML_V1",
        feature_version: str = "VALUATION_FEATURE_SET_V1",
    ) -> None:
        self.model = model
        self.feature_names = feature_names or get_valuation_feature_names()
        self.model_version = model_version
        self.feature_version = feature_version
        self._shap_explainer: Optional[Any] = None
        self._global_importance_: Optional[Dict[str, float]] = None

    def initialize_explainer(self, background_data: Optional[np.ndarray] = None) -> ValuationExplainer:
        """Initialize SHAP explainer on model."""
        try:
            import shap
            # If LightGBM or Tree-based: TreeExplainer
            if hasattr(self.model, "predict"):
                if background_data is not None and len(background_data) > 0:
                    # Sample background up to 100 points for efficiency
                    bg = background_data[:min(100, len(background_data))]
                    self._shap_explainer = shap.Explainer(self.model, bg)
                else:
                    self._shap_explainer = shap.TreeExplainer(self.model)
        except Exception:
            # Fallback will use tree feature importances if SHAP fails
            self._shap_explainer = None
        return self

    def compute_global_importance(self) -> Dict[str, float]:
        """Returns relative feature importance dict sorted descending."""
        if self._global_importance_ is not None:
            return self._global_importance_

        if hasattr(self.model, "feature_importances_"):
            raw_imp = self.model.feature_importances_
            total = float(np.sum(raw_imp)) if np.sum(raw_imp) > 0 else 1.0
            imp = {name: float(val / total) for name, val in zip(self.feature_names, raw_imp)}
        elif hasattr(self.model, "coef_"):
            # Linear model coefficients
            raw_imp = np.abs(self.model.coef_)
            total = float(np.sum(raw_imp)) if np.sum(raw_imp) > 0 else 1.0
            imp = {name: float(val / total) for name, val in zip(self.feature_names, raw_imp)}
        else:
            imp = {name: 1.0 / len(self.feature_names) for name in self.feature_names}

        self._global_importance_ = dict(sorted(imp.items(), key=lambda item: item[1], reverse=True))
        return self._global_importance_

    def explain_instance(
        self,
        player_id: str,
        features: np.ndarray,
        top_k: int = 4,
    ) -> ValuationExplanation:
        """Generates deterministic local explanation for a single player feature vector."""
        if features.ndim == 1:
            features_2d = features.reshape(1, -1)
        else:
            features_2d = features

        pred_log = float(self.model.predict(features_2d)[0])
        attributions: List[Tuple[str, float, float]] = []

        base_val = 0.0
        method = "SHAP"

        if self._shap_explainer is not None:
            try:
                shap_res = self._shap_explainer(features_2d)
                shap_vals = shap_res.values[0]
                base_val = float(shap_res.base_values[0]) if hasattr(shap_res, "base_values") else 0.0
                for name, val, shap_v in zip(self.feature_names, features_2d[0], shap_vals):
                    attributions.append((name, float(val), float(shap_v)))
            except Exception:
                method = "TREE_ATTRIBUTION_FALLBACK"
                attributions = self._compute_heuristic_attribution(features_2d[0], pred_log)
        else:
            method = "TREE_ATTRIBUTION_FALLBACK"
            attributions = self._compute_heuristic_attribution(features_2d[0], pred_log)

        # Sort positive contributors (descending)
        positives = [a for a in attributions if a[2] > 0.0001]
        positives.sort(key=lambda x: x[2], reverse=True)

        # Sort negative contributors (ascending, most negative first)
        negatives = [a for a in attributions if a[2] < -0.0001]
        negatives.sort(key=lambda x: x[2])

        top_pos: List[FeatureAttributionItem] = []
        for rank, (name, val, attr) in enumerate(positives[:top_k], start=1):
            meta = FEATURE_DISPLAY_METADATA.get(name, {"label": name, "unit": "units"})
            narrative = (
                f"{meta['label']} ({val:.2f} {meta['unit']}) contributed positively to the model prediction "
                f"(+{attr:.3f} relative to baseline)."
            )
            top_pos.append(
                FeatureAttributionItem(
                    feature_name=name,
                    display_label=meta["label"],
                    feature_value=val,
                    unit=meta["unit"],
                    attribution_value=attr,
                    direction="POSITIVE",
                    rank=rank,
                    narrative=narrative,
                )
            )

        top_neg: List[FeatureAttributionItem] = []
        for rank, (name, val, attr) in enumerate(negatives[:top_k], start=1):
            meta = FEATURE_DISPLAY_METADATA.get(name, {"label": name, "unit": "units"})
            narrative = (
                f"{meta['label']} ({val:.2f} {meta['unit']}) contributed negatively to the model prediction "
                f"({attr:.3f} relative to baseline)."
            )
            top_neg.append(
                FeatureAttributionItem(
                    feature_name=name,
                    display_label=meta["label"],
                    feature_value=val,
                    unit=meta["unit"],
                    attribution_value=attr,
                    direction="NEGATIVE",
                    rank=rank,
                    narrative=narrative,
                )
            )

        return ValuationExplanation(
            player_id=player_id,
            model_version=self.model_version,
            feature_version=self.feature_version,
            base_value_log=base_val,
            prediction_log=pred_log,
            top_positive_contributors=top_pos,
            top_negative_contributors=top_neg,
            method=method,
        )

    def _compute_heuristic_attribution(
        self,
        features: np.ndarray,
        pred_log: float,
    ) -> List[Tuple[str, float, float]]:
        """Fallback attribution using global feature importance and deviation from reference."""
        importances = self.compute_global_importance()
        res = []
        for name, val in zip(self.feature_names, features):
            imp = importances.get(name, 0.05)
            # Center near typical middle value for attribution sign
            # For rates > 0 positive, for age young is positive (<26)
            if name == "age":
                sign = 1.0 if val < 25.0 else -1.0 if val > 29.0 else 0.0
            elif "per90" in name or "contribution" in name or "minutes" in name:
                sign = 1.0 if val > 0.0 else -1.0
            else:
                sign = 1.0 if val > 0.0 else 0.0
            attr = float(sign * imp * 0.5)
            res.append((name, float(val), attr))
        return res
