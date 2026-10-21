"""Phase 4.2: Transfer Valuation ML Engine — Service Layer.

Orchestrates point-in-time player feature extraction, active model inference,
explanation generation, and comparable transaction evidence linking.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import uuid
from typing import Any, Dict, List, Optional
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.comparables import ComparableTransferEngine
from app.market.context import build_player_market_context
from app.market.dataset import ValuationDatasetBuilder
from app.market.ml.dataset import ValuationMLDatasetBuilder
from app.market.ml.features import FEATURE_NAMES, FEATURE_SET_VERSION
from app.market.ml.gating import ValuationDataStatus
from app.market.ml.registry import (
    ValuationInferenceResult,
    ValuationModelBundle,
    get_valuation_registry,
)
from app.market.schemas import (
    ComparableTransfersResponse,
    MarketContextResponse,
    ValuationMLExplanationResponse,
    ValuationMLPredictionResponse,
    ValuationMLComparablesResponse,
    ValuationModelStatusResponse,
)
from app.market.valuation import BaselineValuationEngine


class ValuationMLService:
    """Production service for ML transfer valuations, explanations, and evidence."""

    @staticmethod
    def _extract_feature_vector(ctx: MarketContextResponse) -> tuple[np.ndarray, int]:
        """Model input vector from REAL point-in-time context only, plus the count of missing values.

        Anything the context cannot supply is NaN and is counted so the sufficiency gate can refuse.
        This replaces a builder that invented values (rating 7.15, goals/90 by position, club tier
        1.0, cohort medians of 25M/18M) and then zero-filled 23 mis-named features via
        ``.get(name, 0.0)``, hiding all of it from the gate.
        """
        pos = getattr(ctx, "position_group", None)
        age = getattr(ctx, "age_at_as_of", None)
        real: Dict[str, float] = {}
        if age is not None:
            real["age_at_transfer"] = float(age)
            real["age_curve_factor"] = float(BaselineValuationEngine.get_age_adjustment(float(age)))
        pos_code = ValuationMLDatasetBuilder.POSITION_ENCODING.get(pos) if pos else None
        if pos_code is not None:
            real["position_group_encoded"] = float(pos_code)
        for name, attr in (
            ("observed_minutes_as_of", "sample_minutes"),
            ("appearances_as_of", "sample_matches"),
            ("total_career_transfers_prior", "total_career_transfers"),
        ):
            value = getattr(ctx, attr, None)
            if value is not None:
                real[name] = float(value)
        vector = np.array([real.get(name, np.nan) for name in FEATURE_NAMES], dtype=np.float32)
        return vector, int(np.isnan(vector).sum())

    @classmethod
    async def get_player_valuation(
        cls,
        session: AsyncSession,
        player_id: uuid.UUID,
        as_of: datetime | None = None,
    ) -> ValuationMLPredictionResponse:
        """Computes point-in-time transfer valuation using the active ML engine."""
        eval_time = as_of or datetime.now(timezone.utc)
        ctx = await build_player_market_context(session, player_id, as_of=eval_time)
        if not ctx:
            raise ValueError(f"Player {player_id} not found in database.")

        registry = get_valuation_registry()
        active_bundle = registry.get_active_model()
        if not active_bundle:
            raise RuntimeError("No active transfer valuation ML model is registered.")

        features, null_count = cls._extract_feature_vector(ctx)
        inference_res = active_bundle.predict_player(
            player_id=str(player_id),
            features=features,
            as_of=eval_time.date().isoformat(),
            minutes_played=ctx.sample_minutes,
            age=ctx.age_at_as_of,
            position_group=ctx.position_group,
            null_count=null_count,
        )

        return ValuationMLPredictionResponse(
            player_id=player_id,
            as_of=eval_time,
            estimated_value_eur=inference_res.estimated_value_eur,
            lower_bound_eur=inference_res.lower_bound_eur,
            upper_bound_eur=inference_res.upper_bound_eur,
            uncertainty_eur=inference_res.uncertainty_eur,
            coverage_level=0.80,
            data_status=inference_res.data_status.value,
            model_version=inference_res.model_version,
            feature_version=inference_res.feature_version,
            algorithm=active_bundle.metadata.algorithm,
            gate_decision=inference_res.gate_decision.to_dict(),
            provenance={
                "model_id": active_bundle.metadata.model_id,
                "dataset_version": active_bundle.metadata.dataset_version,
                "training_period": active_bundle.metadata.training_period,
                "created_at": active_bundle.metadata.created_at,
                "model_release_status": active_bundle.metadata.status,
                "artifact_sha256": registry.active_manifest_entry().get("artifact_sha256"),
                "missing_feature_count": null_count,
                "feature_count": len(FEATURE_NAMES),
            },
        )

    @classmethod
    async def get_player_valuation_explanation(
        cls,
        session: AsyncSession,
        player_id: uuid.UUID,
        as_of: datetime | None = None,
    ) -> ValuationMLExplanationResponse:
        """Returns deterministic SHAP and non-causal feature attributions."""
        eval_time = as_of or datetime.now(timezone.utc)
        ctx = await build_player_market_context(session, player_id, as_of=eval_time)
        if not ctx:
            raise ValueError(f"Player {player_id} not found in database.")

        registry = get_valuation_registry()
        active_bundle = registry.get_active_model()
        if not active_bundle:
            raise RuntimeError("No active transfer valuation ML model is registered.")

        features, null_count = cls._extract_feature_vector(ctx)
        if null_count:
            raise RuntimeError(
                f"Explanation unavailable: {null_count} of {len(FEATURE_NAMES)} model features cannot be "
                "computed from the data currently available for this player."
            )
        exp = active_bundle.explainer.explain_instance(
            player_id=str(player_id),
            features=features,
        )

        return ValuationMLExplanationResponse(
            player_id=player_id,
            as_of=eval_time,
            model_version=exp.model_version,
            feature_version=exp.feature_version,
            method=exp.method,
            base_value_log=exp.base_value_log,
            prediction_log=exp.prediction_log,
            top_positive_contributors=[item.to_dict() for item in exp.top_positive_contributors],
            top_negative_contributors=[item.to_dict() for item in exp.top_negative_contributors],
        )

    @classmethod
    async def get_player_valuation_comparables(
        cls,
        session: AsyncSession,
        player_id: uuid.UUID,
        as_of: datetime | None = None,
        top_k: int = 5,
    ) -> ValuationMLComparablesResponse:
        """Returns model prediction alongside historical comparable transfers evidence."""
        eval_time = as_of or datetime.now(timezone.utc)
        val_res = await cls.get_player_valuation(session, player_id, as_of=eval_time)

        comp_response: ComparableTransfersResponse = await ComparableTransferEngine.find_comparables(
            session, player_id, as_of=eval_time, top_k=top_k
        )

        comparables_list = [
            {
                "player_id": str(c.player_id),
                "player_name": c.player_name,
                "transfer_date": c.transfer_date.isoformat() if c.transfer_date else None,
                "from_club_name": c.from_club_name,
                "to_club_name": c.to_club_name,
                "fee_eur": c.fee_eur,
                "similarity_score": round(c.similarity_score, 4),
                "role_archetype": c.role_archetype,
                "position_group": c.position_group,
            }
            for c in comp_response.comparables
        ]

        return ValuationMLComparablesResponse(
            player_id=player_id,
            as_of=eval_time,
            model_estimated_value_eur=val_res.estimated_value_eur,
            comparable_median_fee_eur=comp_response.cohort_median_fee_eur or 0.0,
            comparables=comparables_list,
        )

    @classmethod
    def get_model_status(cls) -> ValuationModelStatusResponse:
        """Returns the operational status, versioning, and test evaluation metrics."""
        status_dict = get_valuation_registry().get_model_status()
        return ValuationModelStatusResponse(
            active=status_dict.get("active", False),
            status=status_dict.get("status", "NO_ACTIVE_MODEL"),
            model_id=status_dict.get("model_id"),
            model_version=status_dict.get("model_version"),
            dataset_version=status_dict.get("dataset_version"),
            feature_set_version=status_dict.get("feature_set_version"),
            algorithm=status_dict.get("algorithm"),
            created_at=status_dict.get("created_at"),
            test_metrics=status_dict.get("test_metrics", {}),
            release_gate_checklist=status_dict.get("release_gate_checklist", {}),
            message=status_dict.get("message"),
        )
