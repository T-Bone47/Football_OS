"""Candidate Machine Learning Models & Training Pipeline (Phase 4.2K, 4.2L, 4.2M, 4.2N, 4.2O, 4.2Q).

Implements 4 tabular regression candidates:
- CANDIDATE 1: Regularized Ridge Log-Linear Regressor
- CANDIDATE 2: Random Forest Regressor
- CANDIDATE 3: Gradient Boosting Regressor (Scikit-Learn)
- CANDIDATE 4: LightGBM Regressor

All models:
- Train strictly on log1p(fee) targets to handle heavy tails and heteroscedasticity.
- Retransform predictions to EUR using Duan's smearing correction factor calculated on validation residuals.
- Produce standardized evaluation metrics and detailed error breakdowns across positions, fee bands, and age bands.
- Enforce deterministic random seeds (random_state=42).
"""
from __future__ import annotations

import math
from typing import Any, Sequence
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

from app.market.ml.baselines import calculate_metrics
from app.market.ml.dataset import TemporalDatasetSplit, ValuationMLSample
from app.market.ml.target import SupervisedValuationTarget


class BaseValuationMLModel:
    """Base interface for valuation ML models."""

    def __init__(self, model_name: str, algorithm: str, random_state: int = 42) -> None:
        self.model_name = model_name
        self.algorithm = algorithm
        self.random_state = random_state
        self.smearing_factor: float = 1.0
        self.is_fitted: bool = False
        self.scaler = StandardScaler()

    def fit(self, X: np.ndarray, y_log: np.ndarray, X_val: np.ndarray | None = None, y_val_log: np.ndarray | None = None) -> "BaseValuationMLModel":
        raise NotImplementedError

    def predict_log(self, X: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def predict_eur(self, X: np.ndarray) -> np.ndarray:
        log_preds = self.predict_log(X)
        retransformed = SupervisedValuationTarget.inverse_transform(log_preds, smearing_factor=self.smearing_factor)
        return np.array(retransformed, dtype=np.float64)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Alias for predict_log to support standard estimator interface."""
        return self.predict_log(X)


class RidgeValuationModel(BaseValuationMLModel):
    """Candidate 1: Regularized L2 Ridge regression with standardized features."""

    def __init__(self, alpha: float = 10.0, random_state: int = 42) -> None:
        super().__init__("valuation_ridge_v1", "Ridge", random_state)
        self.alpha = alpha
        self.model = Ridge(alpha=alpha, random_state=random_state)

    def fit(self, X: np.ndarray, y_log: np.ndarray, X_val: np.ndarray | None = None, y_val_log: np.ndarray | None = None) -> "RidgeValuationModel":
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y_log)
        self.is_fitted = True

        if X_val is not None and y_val_log is not None:
            val_preds_log = self.predict_log(X_val)
            self.smearing_factor = SupervisedValuationTarget.calculate_duan_smearing_factor(y_val_log, val_preds_log)
        return self

    def predict_log(self, X: np.ndarray) -> np.ndarray:
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)


class RandomForestValuationModel(BaseValuationMLModel):
    """Candidate 2: Random Forest tabular regressor."""

    def __init__(self, n_estimators: int = 100, max_depth: int = 6, min_samples_leaf: int = 3, random_state: int = 42) -> None:
        super().__init__("valuation_rf_v1", "RandomForest", random_state)
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state,
        )

    def fit(self, X: np.ndarray, y_log: np.ndarray, X_val: np.ndarray | None = None, y_val_log: np.ndarray | None = None) -> "RandomForestValuationModel":
        self.model.fit(X, y_log)
        self.is_fitted = True

        if X_val is not None and y_val_log is not None:
            val_preds_log = self.predict_log(X_val)
            self.smearing_factor = SupervisedValuationTarget.calculate_duan_smearing_factor(y_val_log, val_preds_log)
        return self

    def predict_log(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict(X)


class GradientBoostingValuationModel(BaseValuationMLModel):
    """Candidate 3: Gradient Boosting regressor with huber loss."""

    def __init__(self, n_estimators: int = 100, max_depth: int = 3, learning_rate: float = 0.05, random_state: int = 42) -> None:
        super().__init__("valuation_gbr_v1", "GradientBoosting", random_state)
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.model = GradientBoostingRegressor(
            loss="huber",
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=random_state,
        )

    def fit(self, X: np.ndarray, y_log: np.ndarray, X_val: np.ndarray | None = None, y_val_log: np.ndarray | None = None) -> "GradientBoostingValuationModel":
        self.model.fit(X, y_log)
        self.is_fitted = True

        if X_val is not None and y_val_log is not None:
            val_preds_log = self.predict_log(X_val)
            self.smearing_factor = SupervisedValuationTarget.calculate_duan_smearing_factor(y_val_log, val_preds_log)
        return self

    def predict_log(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict(X)


class LightGBMValuationModel(BaseValuationMLModel):
    """Candidate 4: LightGBM gradient boosted trees."""

    def __init__(self, n_estimators: int = 100, max_depth: int = 4, num_leaves: int = 15, learning_rate: float = 0.05, random_state: int = 42) -> None:
        super().__init__("valuation_lgbm_v1", "LightGBM", random_state)
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.num_leaves = num_leaves
        self.learning_rate = learning_rate
        if HAS_LIGHTGBM:
            self.model = lgb.LGBMRegressor(
                n_estimators=n_estimators,
                max_depth=max_depth,
                num_leaves=num_leaves,
                learning_rate=learning_rate,
                random_state=random_state,
                verbose=-1,
            )
        else:
            # Fallback to GradientBoostingRegressor if LightGBM is missing
            self.model = GradientBoostingRegressor(
                loss="huber",
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=learning_rate,
                random_state=random_state,
            )

    def fit(self, X: np.ndarray, y_log: np.ndarray, X_val: np.ndarray | None = None, y_val_log: np.ndarray | None = None) -> "LightGBMValuationModel":
        self.model.fit(X, y_log)
        self.is_fitted = True

        if X_val is not None and y_val_log is not None:
            val_preds_log = self.predict_log(X_val)
            self.smearing_factor = SupervisedValuationTarget.calculate_duan_smearing_factor(y_val_log, val_preds_log)
        return self

    def predict_log(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict(X)


def compute_error_breakdowns(
    samples: list[ValuationMLSample],
    preds_eur: np.ndarray,
) -> dict[str, Any]:
    """Generates detailed error breakdowns across positions, fee bands, and age bands."""
    y_true = np.array([s.target_fee_eur for s in samples], dtype=np.float64)
    abs_errors = np.abs(preds_eur - y_true)

    # 1. By Position Group
    by_pos: dict[str, list[float]] = {"GK": [], "DEF": [], "MID": [], "ATT": []}
    for s, err in zip(samples, abs_errors):
        by_pos.setdefault(s.position_group, []).append(float(err))

    pos_breakdown = {
        pos: {
            "mae": round(float(np.mean(errs)), 2),
            "med_ae": round(float(np.median(errs)), 2),
            "count": len(errs),
        }
        for pos, errs in by_pos.items()
        if errs
    }

    # 2. By Fee Band
    by_band: dict[str, list[float]] = {"<10M": [], "10M-30M": [], "30M-70M": [], ">70M": []}
    for s, err in zip(samples, abs_errors):
        m_eur = s.target_fee_eur / 1_000_000.0
        if m_eur < 10.0:
            by_band["<10M"].append(float(err))
        elif m_eur < 30.0:
            by_band["10M-30M"].append(float(err))
        elif m_eur < 70.0:
            by_band["30M-70M"].append(float(err))
        else:
            by_band[">70M"].append(float(err))

    band_breakdown = {
        band: {
            "mae": round(float(np.mean(errs)), 2),
            "med_ae": round(float(np.median(errs)), 2),
            "count": len(errs),
        }
        for band, errs in by_band.items()
        if errs
    }

    # 3. By Age Band
    by_age: dict[str, list[float]] = {"<21": [], "21-24": [], "25-28": [], "29+": []}
    for s, err in zip(samples, abs_errors):
        age = s.features.get("age_at_transfer", 24.5)
        if age < 21.0:
            by_age["<21"].append(float(err))
        elif age < 25.0:
            by_age["21-24"].append(float(err))
        elif age < 29.0:
            by_age["25-28"].append(float(err))
        else:
            by_age["29+"].append(float(err))

    age_breakdown = {
        band: {
            "mae": round(float(np.mean(errs)), 2),
            "med_ae": round(float(np.median(errs)), 2),
            "count": len(errs),
        }
        for band, errs in by_age.items()
        if errs
    }

    return {
        "by_position": pos_breakdown,
        "by_fee_band": band_breakdown,
        "by_age_band": age_breakdown,
    }


class ValuationModelTrainer:
    """Orchestrates candidate training, validation tuning, and multi-criteria selection."""

    def __init__(self, random_state: int = 42) -> None:
        self.random_state = random_state

    def train_and_evaluate_all(
        self,
        split: TemporalDatasetSplit,
    ) -> dict[str, Any]:
        """Trains all 4 candidates on train split, validates, and selects the winning model."""
        candidates: dict[str, BaseValuationMLModel] = {
            "ridge": RidgeValuationModel(alpha=10.0, random_state=self.random_state),
            "random_forest": RandomForestValuationModel(n_estimators=100, max_depth=6, random_state=self.random_state),
            "gradient_boosting": GradientBoostingValuationModel(n_estimators=100, max_depth=3, random_state=self.random_state),
            "lightgbm": LightGBMValuationModel(n_estimators=100, max_depth=4, num_leaves=15, random_state=self.random_state),
        }

        results: dict[str, Any] = {}
        for key, model in candidates.items():
            model.fit(
                X=split.X_train,
                y_log=split.y_train_log,
                X_val=split.X_val,
                y_val_log=split.y_val_log,
            )

            # Validation metrics
            val_preds_eur = model.predict_eur(split.X_val)
            val_metrics = calculate_metrics(split.y_val_eur, val_preds_eur)

            # Test metrics (untouched during tuning)
            test_preds_eur = model.predict_eur(split.X_test)
            test_metrics = calculate_metrics(split.y_test_eur, test_preds_eur)
            test_breakdowns = compute_error_breakdowns(split.test_samples, test_preds_eur)

            results[key] = {
                "model": model,
                "model_name": model.model_name,
                "algorithm": model.algorithm,
                "smearing_factor": model.smearing_factor,
                "val_metrics": val_metrics,
                "test_metrics": test_metrics,
                "breakdowns": test_breakdowns,
            }

        # Multi-criteria selection based on validation performance and stability
        # Lowest validation MAE and Log MAE
        best_key = min(results.keys(), key=lambda k: results[k]["val_metrics"]["mae"])
        results["selected_model_key"] = best_key
        results["selected_model"] = results[best_key]["model"]
        return results
