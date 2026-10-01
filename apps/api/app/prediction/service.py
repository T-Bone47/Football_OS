"""Match Prediction Service (Phase 6).

Orchestrates the entire leakage-safe match prediction pipeline:
1. Loads target fixture and historical context strictly prior to kickoff (as_of <= kickoff).
2. Generates deterministic pre-match features via PreMatchFeatureBuilder.
3. Gates data sufficiency and detects Out-of-Distribution scenarios via PredictionGatingEngine.
4. Generates strictly normalized 1X2 probabilities via CalibratedMultinomialModel.
5. Derives pre-match expected goals and scoreline distribution via GoalPredictionEngine.
6. Synthesizes non-causal evidence factor breakdown via MatchExplanationEngine.
7. Maintains snapshot audit trail for point-in-time reproducibility.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import Club, Match
from app.prediction.elo import EloRatingEngine
from app.prediction.explain import MatchExplanationEngine
from app.prediction.features import PreMatchFeatureBuilder, PredictionSnapshot
from app.prediction.gating import PredictionGatingEngine
from app.prediction.goals import GoalPredictionEngine
from app.prediction.models import (
    CLASS_PRIOR_AWAY,
    CLASS_PRIOR_DRAW,
    CLASS_PRIOR_HOME,
    BaselineClassFrequencyModel,
    CalibratedMultinomialModel,
    normalize_probabilities,
)
from app.prediction.registry import model_registry
from app.prediction.schemas import (
    CalibrationInfo,
    ExpectedGoals,
    GoalDistribution,
    MatchPredictionHistoryItem,
    MatchPredictionHistoryResponse,
    MatchPredictionResponse,
    ModelStatusResponse,
    OutcomeProbabilities,
    PredictionExplanation,
    ScorelineProbability,
)


class MatchPredictionService:
    """Production service for probabilistic football match intelligence."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session
        self.elo_engine = EloRatingEngine()
        self.feature_builder = PreMatchFeatureBuilder(elo_engine=self.elo_engine)
        self.gating_engine = PredictionGatingEngine()
        self.active_model = CalibratedMultinomialModel(temperature=1.06)
        self.goal_engine = GoalPredictionEngine()
        self.explanation_engine = MatchExplanationEngine()
        self.fallback_model = BaselineClassFrequencyModel()

        # In-memory history cache keyed by match_id for fast temporal audits
        self._prediction_history_cache: dict[uuid.UUID, list[MatchPredictionHistoryItem]] = {}

    async def predict_match(
        self,
        match_id: uuid.UUID,
        as_of: datetime | None = None,
        historical_matches_override: list[Any] | None = None,
    ) -> MatchPredictionResponse:
        """Computes a temporally valid, leakage-safe prediction for the specified match."""
        # 1. Fetch match and clubs
        match = None
        home_club = None
        away_club = None

        if self._session is not None:
            stmt = (
                select(Match)
                .options(
                    selectinload(Match.home_club),
                    selectinload(Match.away_club),
                )
                .where(Match.id == match_id)
            )
            match = (await self._session.execute(stmt)).scalar_one_or_none()

        if match is not None:
            home_club_id = match.home_club_id
            away_club_id = match.away_club_id
            home_club_name = match.home_club.name if match.home_club else "Home Club"
            away_club_name = match.away_club.name if match.away_club else "Away Club"
            kickoff_time = match.date
            competition_id = match.competition_season_id
        elif historical_matches_override:
            # Fallback for unit testing without db session
            home_club_id = uuid.uuid4()
            away_club_id = uuid.uuid4()
            home_club_name = "Home Club"
            away_club_name = "Away Club"
            kickoff_time = datetime.now(timezone.utc)
            competition_id = None
        else:
            raise ValueError(f"Match with ID {match_id} not found.")

        # 2. Strict Pre-Match Cutoff
        eval_cutoff = as_of if as_of is not None else kickoff_time
        cutoff = min(kickoff_time, eval_cutoff)

        # 3. Retrieve Historical Matches
        past_matches = []
        if historical_matches_override is not None:
            past_matches = list(historical_matches_override)
        elif self._session is not None:
            hist_stmt = (
                select(Match)
                .where(
                    Match.date < cutoff,
                    Match.id != match_id,
                    or_(
                        Match.home_club_id.in_([home_club_id, away_club_id]),
                        Match.away_club_id.in_([home_club_id, away_club_id]),
                    ),
                )
                .order_by(Match.date.asc())
            )
            past_matches = list((await self._session.execute(hist_stmt)).scalars().all())

        # 4. Build Pre-Match Feature Snapshot
        snapshot = self.feature_builder.build_features(
            match_id=match_id,
            home_club_id=home_club_id,
            away_club_id=away_club_id,
            kickoff_time=kickoff_time,
            historical_matches=past_matches,
            as_of=cutoff,
            competition_id=competition_id,
        )

        # 5. Gating & Data Sufficiency Check
        gating_res = self.gating_engine.evaluate(
            features=snapshot.features,
            home_sample_size=snapshot.home_sample_size,
            away_sample_size=snapshot.away_sample_size,
            h2h_sample_size=snapshot.h2h_sample_size,
        )

        active_meta = model_registry.get_active_model()

        # 6. Generate Probabilities
        if gating_res.status == "INSUFFICIENT_DATA":
            # Fallback to empirical priors; no fabricated confidence
            probs = self.fallback_model.predict(snapshot.features)
            xg = ExpectedGoals(home=1.35, away=1.15, total=2.50)
            goal_dist = self.goal_engine.generate_scoreline_distribution(xg)
            cal_info = CalibrationInfo(
                status="RAW",
                method="NONE",
                brier_score=None,
                expected_calibration_error=None,
            )
            explanation = PredictionExplanation(
                summary="Insufficient historical fixture data available prior to kickoff. "
                        "Probabilities reflect global historical league outcome distribution.",
                key_factors=[],
                home_strengths=[],
                away_strengths=[],
                context_notes=gating_res.reasons,
            )
        else:
            # Calibrated ML Model
            raw_probs = self.active_model.predict(snapshot.features)

            # If low confidence, soften probabilities toward league priors
            if gating_res.status in ("LOW_CONFIDENCE", "OUT_OF_DISTRIBUTION"):
                w = gating_res.confidence_multiplier
                h = w * raw_probs.home_win + (1 - w) * CLASS_PRIOR_HOME
                d = w * raw_probs.draw + (1 - w) * CLASS_PRIOR_DRAW
                a = w * raw_probs.away_win + (1 - w) * CLASS_PRIOR_AWAY
                probs = normalize_probabilities(h, d, a)
            else:
                probs = raw_probs

            # Compute Expected Goals (xG)
            h_att = snapshot.features.get("home_attack_strength") or 1.0
            h_def = snapshot.features.get("home_defense_strength") or 1.0
            a_att = snapshot.features.get("away_attack_strength") or 1.0
            a_def = snapshot.features.get("away_defense_strength") or 1.0
            xg = self.goal_engine.compute_expected_goals(h_att, h_def, a_att, a_def)
            goal_dist = self.goal_engine.generate_scoreline_distribution(xg)

            cal_info = CalibrationInfo(
                status="CALIBRATED",
                method=active_meta.calibration_method,
                brier_score=active_meta.metrics.get("brier_score"),
                expected_calibration_error=active_meta.metrics.get("ece"),
            )

            # Generate Feature Attribution Explanation
            explanation = self.explanation_engine.explain(
                home_club_name=home_club_name,
                away_club_name=away_club_name,
                features=snapshot.features,
                p_home=probs.home_win,
                p_draw=probs.draw,
                p_away=probs.away_win,
            )
            explanation.context_notes.extend(gating_res.reasons)

        now_utc = datetime.now(timezone.utc)
        response = MatchPredictionResponse(
            match_id=match_id,
            as_of=cutoff,
            home_club_id=home_club_id,
            home_club_name=home_club_name,
            away_club_id=away_club_id,
            away_club_name=away_club_name,
            probabilities=probs,
            expected_goals=xg,
            goal_distribution=goal_dist,
            calibration=cal_info,
            model_version=active_meta.model_version,
            feature_version=snapshot.feature_version,
            data_status=gating_res.status,
            data_sufficiency_reasons=gating_res.reasons,
            explanation=explanation,
            evaluated_at=now_utc,
        )

        # Cache history record for audit
        history_item = MatchPredictionHistoryItem(
            prediction_time=now_utc,
            as_of=cutoff,
            probabilities=probs,
            expected_goals=xg,
            model_version=active_meta.model_version,
            data_status=gating_res.status,
        )
        if match_id not in self._prediction_history_cache:
            self._prediction_history_cache[match_id] = []
        self._prediction_history_cache[match_id].append(history_item)

        return response

    async def get_prediction_explanation(
        self,
        match_id: uuid.UUID,
        as_of: datetime | None = None,
    ) -> PredictionExplanation:
        """Returns the non-causal explainability factor breakdown for a match."""
        prediction = await self.predict_match(match_id=match_id, as_of=as_of)
        return prediction.explanation

    async def get_prediction_history(
        self,
        match_id: uuid.UUID,
    ) -> MatchPredictionHistoryResponse:
        """Returns the historical prediction snapshots generated for a match."""
        if match_id not in self._prediction_history_cache:
            # Generate current prediction to populate history
            try:
                await self.predict_match(match_id=match_id)
            except Exception:
                pass

        history = self._prediction_history_cache.get(match_id, [])
        return MatchPredictionHistoryResponse(
            match_id=match_id,
            history=history,
        )

    def get_model_status(self) -> ModelStatusResponse:
        """Returns the verified operational and calibration metrics of the active model."""
        return model_registry.get_status_response()
