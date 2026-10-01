"""End-to-End Decision & Intelligence Workflows (Phase 8 Section 2).

Validates the complete execution pipelines:
WORKFLOW A: Recruitment:
  User requirement -> hard constraints -> candidate universe -> intelligence ->
  tactical fit -> similarity -> valuation -> risk -> squad impact ->
  evidence DAG -> decision assessment

WORKFLOW B: Replacement:
  Player -> replacement profile -> candidates -> comparison ->
  market -> risk -> scenario -> evidence

WORKFLOW C: Transfer Scenario:
  Squad -> transfer in/out -> squad analysis -> financial impact ->
  tactical impact -> match scenario -> decision trace

WORKFLOW D: Match Intelligence:
  Match -> pre-match features -> prediction -> calibration ->
  expected goals -> scoreline distribution -> explanation -> model status

All workflows must preserve provenance and trace integrity.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
import pytest

from app.decisions.recruitment import RecruitmentTargetEngine
from app.decisions.replacement import ReplacementDecisionEngine
from app.decisions.scenario import DecisionTransferScenarioEngine
from app.decisions.schemas import (
    ConfidenceDecomposition,
    DimensionMarket,
    DimensionPerformance,
    DimensionPredictionImpact,
    DimensionRisk,
    DimensionSimilarity,
    DimensionSquadImpact,
    DimensionTactical,
    HardConstraintResult,
    MultiDimensionalCandidateAssessment,
    RecruitmentTargetRequest,
    ReplacementDecisionRequest,
    ScenarioRosterChange,
    TransferScenarioDecisionRequest,
)
from app.decisions.service import DecisionNotFound, UnifiedDecisionService
from app.observability.model_governance import governance_registry
from app.prediction.explain import MatchExplanationEngine
from app.prediction.goals import GoalPredictionEngine
from app.prediction.models import normalize_probabilities
from app.prediction.schemas import ExpectedGoals, OutcomeProbabilities


def _make_candidate(
    cid: str,
    name: str,
    pos: str = "MF",
    role: str = "Playmaker",
    fee: float = 20_000_000.0,
    score: float = 82.0,
    minutes: int = 1500,
    age: float = 24.0,
) -> MultiDimensionalCandidateAssessment:
    return MultiDimensionalCandidateAssessment(
        candidate_id=uuid.UUID(cid),
        player_name=name,
        primary_position=pos,
        target_role=role,
        age=age,
        current_club_name="Benchmark FC",
        minutes_played=minutes,
        hard_constraints=HardConstraintResult(passed=True, checks={"min_minutes": True, "age_window": True}),
        performance=DimensionPerformance(contribution_rating=score, percentile_in_role=80.0),
        tactical=DimensionTactical(
            tactical_fit_score=score,
            role_compatibility=82.0,
            system_name="possession_dominant_433",
            target_role=role,
            strengths=["High progressive passing", "Role conformity"],
        ),
        similarity=DimensionSimilarity(overall_similarity=0.85, statistical_similarity=0.82, role_similarity=0.88),
        market=DimensionMarket(
            estimated_value_eur=fee,
            fee_range_low_eur=fee * 0.85,
            fee_range_high_eur=fee * 1.15,
            value_opportunity_index=1.10,
        ),
        risk=DimensionRisk(
            overall_risk_score=0.28,
            performance_risk=0.22,
            adaptation_risk=0.30,
            financial_risk=0.25,
            availability_risk=0.15,
            risk_level="LOW",
            key_risk_drivers=["League adaptation horizon"],
        ),
        squad_impact=DimensionSquadImpact(formation_slot="Central Midfield", net_squad_upgrade=True),
        prediction_impact=DimensionPredictionImpact(),
        confidence=ConfidenceDecomposition(
            data_confidence=0.88,
            model_confidence=0.85,
            decision_confidence=0.86,
            confidence_tier="HIGH",
            data_status="DECISION_AVAILABLE",
        ),
        hard_constraints_passed=True,
    )


class TestWorkflowARecruitment:
    """WORKFLOW A: Full Recruitment Target Evaluation & Traceability."""

    @pytest.mark.asyncio
    async def test_recruitment_workflow_end_to_end(self):
        service = UnifiedDecisionService(session=None)
        t0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        req = RecruitmentTargetRequest(
            target_position="MF",
            target_role="Playmaker",
            tactical_context_id="possession_dominant_433",
            budget_eur=35_000_000.0,
            as_of=t0,
        )

        c1 = _make_candidate("00000000-0000-0000-0000-000000000001", "Florian Wirtz", fee=30_000_000.0, score=89.0)
        c2 = _make_candidate("00000000-0000-0000-0000-000000000002", "Alex Baena", fee=22_000_000.0, score=84.0)

        response = await service.analyze_recruitment_targets(req, candidates_override=[c1, c2])

        # 1. Output object validity
        assert response.decision is not None
        assert response.decision.decision_type == "RECRUITMENT"
        assert response.decision.as_of == t0

        # 2. Recommendations ranking & dimensions
        assert len(response.top_recommendations) == 2
        top = response.top_recommendations[0]
        assert top.player_name == "Florian Wirtz"
        assert top.performance.contribution_rating == 89.0
        assert top.tactical.tactical_fit_score == 89.0
        # Confidence is computed by the engine from the evidence present, never taken from the caller.
        assert top.dimension_status["performance"] == "SUPPLIED"
        assert top.confidence.confidence_tier in ("HIGH", "MODERATE", "LOW", "VERY_LOW")

        # 3. Evidence DAG & hash (no in-memory cache: without a persistent store nothing is retrievable)
        ev_graph = response.decision.evidence_graph
        assert ev_graph.evidence_hash == response.decision.evidence_hash != ""
        node_types = {n.node_type for n in ev_graph.nodes}
        assert {"PLAYER", "CONTRIBUTION", "TACTICAL_FIT", "VALUATION", "RISK", "SQUAD", "DECISION"} <= node_types
        with pytest.raises(DecisionNotFound):
            await service.get_decision(response.decision.decision_id)

        # 4. Provenance preservation
        assert response.decision.provenance["tactical_context"] == "possession_dominant_433"
        assert response.decision.provenance["target_position"] == "MF"


class TestWorkflowBReplacement:
    """WORKFLOW B: Player Replacement Evaluation & Comparative Analysis."""

    @pytest.mark.asyncio
    async def test_replacement_workflow_end_to_end(self):
        service = UnifiedDecisionService(session=None)
        t0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        target_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
        req = ReplacementDecisionRequest(
            player_id_to_replace=target_id,
            target_role="Playmaker",
            budget_eur=50_000_000.0,
            as_of=t0,
        )

        departing = _make_candidate(str(target_id), "Kevin De Bruyne", fee=45_000_000.0, score=92.0)
        c1 = _make_candidate("00000000-0000-0000-0000-000000000010", "Dominik Szoboszlai", fee=40_000_000.0, score=86.0)

        response = await service.analyze_replacement(
            req,
            target_player_override=departing,
            candidates_override=[c1],
        )

        assert response.replaced_player_name == "Kevin De Bruyne"
        assert len(response.top_replacements) == 1
        assert response.top_replacements[0].player_name == "Dominik Szoboszlai"
        assert response.decision.decision_type == "REPLACEMENT"
        assert response.decision.evidence_hash != ""

        # Provenance connects departing player to replacement decision
        assert response.decision.provenance["replaced_player_name"] == "Kevin De Bruyne"
        assert response.decision.provenance["replaced_player_id"] == str(target_id)


class TestWorkflowCTransferScenario:
    """WORKFLOW C: Transfer Scenario Modeling & Roster Transition."""

    @pytest.mark.asyncio
    async def test_transfer_scenario_workflow_end_to_end(self):
        service = UnifiedDecisionService(session=None)
        t0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        club_id = uuid.UUID("00000000-0000-0000-0000-000000000100")
        p_in = uuid.UUID("00000000-0000-0000-0000-000000000021")
        p_out = uuid.UUID("00000000-0000-0000-0000-000000000022")

        req = TransferScenarioDecisionRequest(
            club_id=club_id,
            roster_changes=[
                ScenarioRosterChange(player_id=p_in, direction="IN", fee_eur=30_000_000.0),
                ScenarioRosterChange(player_id=p_out, direction="OUT", fee_eur=20_000_000.0),
            ],
            budget_eur=60_000_000.0,
            formation="4-3-3",
            as_of=t0,
        )

        response = await service.simulate_transfer_scenario(req)

        # 1. Decision assessment
        assert response.decision.decision_type == "TRANSFER_SCENARIO"
        assert response.decision.subject_id == club_id
        assert response.decision.evidence_hash != ""

        # 2. Financial tracking
        assert response.financial_impact["total_expenditure_eur"] == 30_000_000.0
        assert response.financial_impact["total_income_eur"] == 20_000_000.0
        assert response.financial_impact["net_transfer_spend_eur"] == 10_000_000.0
        assert response.financial_impact["financial_feasibility"] == "FEASIBLE"

        # 3. Squad and match impact trace
        assert response.squad_impact_summary["formation"] == "4-3-3"
        assert "risk_profile_before" in response.model_dump()
        assert "risk_profile_after" in response.model_dump()
        assert response.decision.provenance["club_id"] == str(club_id)


class TestWorkflowDMatchIntelligence:
    """WORKFLOW D: Match Prediction, Calibration, Scorelines & Model Governance."""

    def test_match_intelligence_workflow_end_to_end(self):
        # 1. Phase 18: no match model is registered with backing evidence, so
        #    governance must refuse it rather than vouch for a literal record.
        from app.observability.model_governance import UnknownModelVersionError
        with pytest.raises(UnknownModelVersionError):
            governance_registry.verify_inference_eligibility("match_prediction_engine", "BivariatePoisson_v1")

        # 2. Compute Expected Goals from Dixon-Coles/Poisson engine
        goal_engine = GoalPredictionEngine()
        xg = goal_engine.compute_expected_goals(
            home_attack_strength=1.3,
            home_defense_strength=0.8,
            away_attack_strength=1.0,
            away_defense_strength=1.1,
        )
        assert xg.home > 0.0
        assert xg.away > 0.0

        # 3. Scoreline probability matrix & Outcome probabilities
        distribution = goal_engine.generate_scoreline_distribution(xg)
        assert len(distribution.top_scorelines) > 0
        assert distribution.over_2_5 > 0.0

        p_home, p_draw, p_away = goal_engine.scorelines_to_1x2(distribution)
        total_p = p_home + p_draw + p_away
        assert abs(total_p - 1.0) < 1e-3

        # 4. Generate Non-Causal Explanation
        features = {
            "elo_diff": 120.0,
            "home_elo": 1820.0,
            "away_elo": 1700.0,
            "home_points_l5": 2.2,
            "away_points_l5": 1.4,
            "points_diff_l5": 0.8,
            "home_attack_strength": 1.3,
            "away_defense_strength": 1.1,
            "away_attack_strength": 1.0,
            "home_defense_strength": 0.8,
            "home_rest_days": 6.0,
            "away_rest_days": 3.0,
            "rest_days_diff": 3.0,
        }
        explainer = MatchExplanationEngine()
        explanation = explainer.explain(
            home_club_name="Arsenal",
            away_club_name="Chelsea",
            features=features,
            p_home=p_home,
            p_draw=p_draw,
            p_away=p_away,
        )
        assert len(explanation.key_factors) >= 1
        assert "contributing" in explanation.summary.lower() or "model estimates" in explanation.summary.lower()
        assert len(explanation.context_notes) >= 2
        assert "future goals" in explanation.context_notes[1].lower()

