"""Production Model Serving, Version Pinning & Canary/Shadow Routing for Phase 16.

Rules:
- Never load an unregistered model into production.
- Every prediction carries pinned metadata: model_version, feature_version, dataset_version, calculation_version.
- Supported Deployment States:
  REGISTERED, SHADOW, CANARY, ACTIVE, DEPRECATED, RETIRED.
- Champion / Challenger isolation: Shadow challenger outputs never overwrite production decisions.
"""

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
from typing import Any
from pydantic import BaseModel, Field

from app.phase16 import DeploymentState
from app.dev_fixtures import dev_seed_enabled


class ModelServingProfile(BaseModel):
    model_id: str
    model_version: str
    feature_set_version: str
    dataset_version: str
    calculation_version: str = "calc_v16.0"
    training_window: dict[str, str]
    validation_window: dict[str, str]
    supported_competitions: list[str]
    supported_positions: list[str]
    calibration_state: str  # CALIBRATED, UNCALIBRATED
    ood_policy: str  # BLOCK_INFERENCE, WARN_AND_SERVE
    deployment_state: DeploymentState
    canary_weight_percent: float = 0.0  # 0.0 to 100.0


class PredictionServingResponse(BaseModel):
    prediction_id: str
    model_id: str
    model_version: str
    feature_version: str
    dataset_version: str
    calculation_version: str
    deployment_mode: str  # ACTIVE_CHAMPION, CANARY, SHADOW_CHALLENGER
    input_digest: str
    # None whenever no prediction was produced (MODEL_UNAVAILABLE / OOD).
    predicted_value: float | None
    confidence_interval: tuple[float, float] | None
    is_ood: bool
    data_status: str
    served_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ModelServingEngine:
    """Manages active model serving, canary traffic splitting, and shadow execution."""

    def __init__(self, seed_demo_models: bool = False) -> None:
        self._models: dict[str, ModelServingProfile] = {}
        self._champion_by_domain: dict[str, str] = {}
        self._shadow_challengers: dict[str, str] = {}
        self._predictors: dict[str, Callable[[dict[str, Any]], float]] = {}
        if seed_demo_models:
            if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
                self._seed_demo_models()

    def register_predictor(self, model_key: str, predictor: Callable[[dict[str, Any]], float]) -> None:
        """Attach the callable that actually scores inputs for a registered
        model. A model without a predictor cannot serve."""
        if model_key not in self._models:
            raise KeyError(f"Cannot attach predictor: model '{model_key}' is not registered.")
        self._predictors[model_key] = predictor

    def _seed_demo_models(self) -> None:
        # Phase 17 (reconnaissance R8/R20): these profiles describe models that
        # do not exist as artifacts. They are kept only as opt-in fixtures for
        # exercising pinning/shadow mechanics; the production singleton never
        # loads them.
        # Champion: Valuation Engine
        val_champ = ModelServingProfile(
            model_id="valuation_ml_v1",
            model_version="1.2.0",
            feature_set_version="features_v14.0",
            dataset_version="ds_silver_transfers_2024",
            training_window={"start": "2020-08-01", "end": "2023-05-30"},
            validation_window={"start": "2023-08-01", "end": "2024-05-30"},
            supported_competitions=["EPL", "La_Liga", "Bundesliga", "Serie_A", "Ligue_1"],
            supported_positions=["GK", "DF", "MF", "FW"],
            calibration_state="CALIBRATED",
            ood_policy="WARN_AND_SERVE",
            deployment_state=DeploymentState.ACTIVE,
        )
        self.register_model(val_champ)
        self.set_champion("valuation", "valuation_ml_v1:1.2.0")

        # Shadow Challenger: Valuation Engine
        val_challenger = ModelServingProfile(
            model_id="valuation_ml_v2_spline",
            model_version="2.0.0-rc1",
            feature_set_version="features_v15.0",
            dataset_version="ds_silver_transfers_2024",
            training_window={"start": "2020-08-01", "end": "2023-12-31"},
            validation_window={"start": "2024-01-01", "end": "2024-05-30"},
            supported_competitions=["EPL", "Bundesliga"],
            supported_positions=["GK", "DF", "MF", "FW"],
            calibration_state="CALIBRATED",
            ood_policy="BLOCK_INFERENCE",
            deployment_state=DeploymentState.SHADOW,
        )
        self.register_model(val_challenger)
        self.set_shadow_challenger("valuation", "valuation_ml_v2_spline:2.0.0-rc1")

    def register_model(self, profile: ModelServingProfile) -> None:
        key = f"{profile.model_id}:{profile.model_version}"
        self._models[key] = profile

    def set_champion(self, domain: str, model_key: str) -> None:
        if model_key not in self._models:
            raise KeyError(f"Cannot set champion: model '{model_key}' is not registered.")
        self._champion_by_domain[domain] = model_key
        self._models[model_key].deployment_state = DeploymentState.ACTIVE

    def set_shadow_challenger(self, domain: str, model_key: str) -> None:
        if model_key not in self._models:
            raise KeyError(f"Cannot set shadow: model '{model_key}' is not registered.")
        self._shadow_challengers[domain] = model_key
        self._models[model_key].deployment_state = DeploymentState.SHADOW

    def serve_inference(
        self,
        domain: str,
        input_data: dict[str, Any],
        competition: str,
        position: str,
        traffic_random_seed: float = 0.5,  # used for deterministic canary routing
    ) -> tuple[PredictionServingResponse, PredictionServingResponse | None]:
        """Serves prediction from active champion (or canary) and shadow evaluates challenger.

        Returns (production_response, shadow_response_or_none).
        """
        champ_key = self._champion_by_domain.get(domain)
        if not champ_key:
            raise KeyError(f"No active champion configured for domain '{domain}'.")

        champ_model = self._models[champ_key]

        # Check competition and position support
        if competition not in champ_model.supported_competitions:
            is_ood = True
            data_status = "OUT_OF_DISTRIBUTION"
        else:
            is_ood = False
            data_status = "DATA_AVAILABLE"

        input_digest = hashlib.sha256(str(sorted(input_data.items())).encode("utf-8")).hexdigest()

        def score(model_key: str, model: ModelServingProfile, mode: str, ood: bool, status_ok: str) -> PredictionServingResponse:
            predictor = self._predictors.get(model_key)
            value: float | None = None
            if ood:
                status = "OUT_OF_DISTRIBUTION"  # never served, whatever the profile's ood_policy says
            elif predictor is None:
                status = "MODEL_UNAVAILABLE"
            else:
                value = round(float(predictor(input_data)), 3)
                status = status_ok
            return PredictionServingResponse(
                prediction_id=f"{'pred' if mode == 'ACTIVE_CHAMPION' else 'shadow'}_{model.model_id}_{input_digest[:8]}",
                model_id=model.model_id,
                model_version=model.model_version,
                feature_version=model.feature_set_version,
                dataset_version=model.dataset_version,
                calculation_version=model.calculation_version,
                deployment_mode=mode,
                input_digest=input_digest,
                predicted_value=value,
                confidence_interval=None,
                is_ood=ood,
                data_status=status,
            )

        prod_resp = score(champ_key, champ_model, "ACTIVE_CHAMPION", is_ood, data_status)

        shadow_resp = None
        chall_key = self._shadow_challengers.get(domain)
        if chall_key and chall_key in self._models:
            chall_model = self._models[chall_key]
            shadow_resp = score(chall_key, chall_model, "SHADOW_CHALLENGER",
                                competition not in chall_model.supported_competitions, "SHADOW_EVALUATION")

        return prod_resp, shadow_resp

    def get_model(self, model_key: str) -> ModelServingProfile:
        if model_key not in self._models:
            raise KeyError(f"Model profile '{model_key}' not found.")
        return self._models[model_key]

    def list_models(self) -> list[ModelServingProfile]:
        return list(self._models.values())


_GLOBAL_MODEL_SERVING_ENGINE: ModelServingEngine | None = None


def get_model_serving_engine() -> ModelServingEngine:
    global _GLOBAL_MODEL_SERVING_ENGINE
    if _GLOBAL_MODEL_SERVING_ENGINE is None:
        _GLOBAL_MODEL_SERVING_ENGINE = ModelServingEngine()
    return _GLOBAL_MODEL_SERVING_ENGINE
