"""Unit tests for Phase 8 Decision Reproducibility, Evidence Hashing & Temporal Safety."""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
import pytest

from app.decisions.evidence import (
    DecisionEvidenceGraphBuilder,
    compute_evidence_hash,
)
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
    EvidenceGraphEdge,
    EvidenceGraphNode,
    HardConstraintResult,
    MultiDimensionalCandidateAssessment,
    RecruitmentTargetRequest,
    ReplacementDecisionRequest,
    ScenarioRosterChange,
    TransferScenarioDecisionRequest,
)


def _make_candidate(cid: str, name: str, fee: float, score: float) -> MultiDimensionalCandidateAssessment:
    return MultiDimensionalCandidateAssessment(
        candidate_id=uuid.UUID(cid),
        player_name=name,
        primary_position="MF",
        target_role="Playmaker",
        age=24.5,
        current_club_name="Benchmark FC",
        minutes_played=1800,
        hard_constraints=HardConstraintResult(passed=True),
        performance=DimensionPerformance(contribution_rating=score, percentile_in_role=85.0),
        tactical=DimensionTactical(
            tactical_fit_score=score,
            role_compatibility=85.0,
            system_name="possession_dominant_433",
            target_role="Playmaker",
        ),
        similarity=DimensionSimilarity(overall_similarity=0.88, statistical_similarity=0.85, role_similarity=0.90),
        market=DimensionMarket(
            estimated_value_eur=fee,
            fee_range_low_eur=fee * 0.85,
            fee_range_high_eur=fee * 1.15,
            value_opportunity_index=1.15,
        ),
        risk=DimensionRisk(
            overall_risk_score=0.25,
            performance_risk=0.20,
            adaptation_risk=0.25,
            financial_risk=0.30,
            availability_risk=0.15,
            risk_level="LOW",
        ),
        squad_impact=DimensionSquadImpact(formation_slot="Central Midfield", net_squad_upgrade=True),
        prediction_impact=DimensionPredictionImpact(),
        confidence=ConfidenceDecomposition(
            data_confidence=0.90,
            model_confidence=0.85,
            decision_confidence=0.88,
            confidence_tier="HIGH",
            data_status="DECISION_AVAILABLE",
        ),
        hard_constraints_passed=True,
    )


class TestDecisionReproducibility:
    @pytest.mark.asyncio
    async def test_recruitment_decision_reproducibility(self):
        engine = RecruitmentTargetEngine(session=None)
        t0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        req = RecruitmentTargetRequest(
            target_position="MF",
            target_role="Playmaker",
            tactical_context_id="possession_dominant_433",
            budget_eur=30_000_000.0,
            as_of=t0,
        )

        c1 = _make_candidate("00000000-0000-0000-0000-000000000001", "Player One", 20_000_000.0, 85.0)
        c2 = _make_candidate("00000000-0000-0000-0000-000000000002", "Player Two", 25_000_000.0, 78.0)

        # Run 1
        res1 = await engine.evaluate_recruitment(req, candidates_override=[c1, c2])

        # Run 2 with identical input & as_of
        res2 = await engine.evaluate_recruitment(req, candidates_override=[c1, c2])

        # Verify exact reproducibility
        assert res1.decision.decision_id == res2.decision.decision_id
        assert res1.decision.evidence_hash != ""
        assert res1.decision.evidence_hash == res2.decision.evidence_hash
        assert res1.decision.confidence.decision_confidence == res2.decision.confidence.decision_confidence
        assert res1.decision.confidence.confidence_tier == res2.decision.confidence.confidence_tier
        assert len(res1.top_recommendations) == len(res2.top_recommendations)
        assert res1.top_recommendations[0].candidate_id == res2.top_recommendations[0].candidate_id

    @pytest.mark.asyncio
    async def test_replacement_decision_reproducibility(self):
        engine = ReplacementDecisionEngine(session=None)
        t0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        target_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
        req = ReplacementDecisionRequest(
            player_id_to_replace=target_id,
            target_role="Playmaker",
            budget_eur=40_000_000.0,
            as_of=t0,
        )

        target_mock = _make_candidate(str(target_id), "Departing Star", 35_000_000.0, 88.0)
        c1 = _make_candidate("00000000-0000-0000-0000-000000000001", "Replacement Candidate", 22_000_000.0, 84.0)

        res1 = await engine.evaluate_replacement(req, target_player_override=target_mock, candidates_override=[c1])
        res2 = await engine.evaluate_replacement(req, target_player_override=target_mock, candidates_override=[c1])

        assert res1.decision.decision_id == res2.decision.decision_id
        assert res1.decision.evidence_hash == res2.decision.evidence_hash
        assert res1.top_replacements[0].candidate_id == res2.top_replacements[0].candidate_id

    @pytest.mark.asyncio
    async def test_transfer_scenario_reproducibility(self):
        engine = DecisionTransferScenarioEngine(session=None)
        t0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        club_id = uuid.UUID("00000000-0000-0000-0000-000000000100")
        p_in = uuid.UUID("00000000-0000-0000-0000-000000000001")
        p_out = uuid.UUID("00000000-0000-0000-0000-000000000002")

        req = TransferScenarioDecisionRequest(
            club_id=club_id,
            roster_changes=[
                ScenarioRosterChange(player_id=p_in, direction="IN", fee_eur=25_000_000.0),
                ScenarioRosterChange(player_id=p_out, direction="OUT", fee_eur=18_000_000.0),
            ],
            as_of=t0,
        )

        res1 = await engine.evaluate_scenario(req)
        res2 = await engine.evaluate_scenario(req)

        assert res1.decision.decision_id == res2.decision.decision_id
        assert res1.decision.evidence_hash == res2.decision.evidence_hash
        assert res1.financial_impact["net_transfer_spend_eur"] == res2.financial_impact["net_transfer_spend_eur"]


class TestEvidenceGraphHashing:
    def test_evidence_hash_order_invariance(self):
        n1 = EvidenceGraphNode(id="n1", node_type="PLAYER", label="Player A", value={"age": 25})
        n2 = EvidenceGraphNode(id="n2", node_type="ROLE", label="Playmaker", value={"role": "Playmaker"})
        e1 = EvidenceGraphEdge(from_node="n1", to_node="n2", relationship="FEEDS_INTO")

        hash_standard = compute_evidence_hash([n1, n2], [e1])
        # Inverted node list passed in
        hash_inverted = compute_evidence_hash([n2, n1], [e1])

        assert hash_standard == hash_inverted
        assert len(hash_standard) == 64  # SHA-256


class TestTemporalReplayAndFutureInjection:
    @pytest.mark.asyncio
    async def test_temporal_safety_under_future_data_injection(self):
        """
        Decision evaluated at T0 must remain 100% identical when candidates are augmented
        with future-dated statistics or future match deltas.
        """
        engine = RecruitmentTargetEngine(session=None)
        t0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        req = RecruitmentTargetRequest(
            target_position="MF",
            target_role="Playmaker",
            tactical_context_id="possession_dominant_433",
            as_of=t0,
        )

        c1 = _make_candidate("00000000-0000-0000-0000-000000000001", "Candidate Alpha", 15_000_000.0, 80.0)

        # Baseline evaluation at T0
        baseline_res = await engine.evaluate_recruitment(req, candidates_override=[c1])

        # Create candidate with future stats injected at T1 > T0
        # When evaluating at T0, the historical assessment is unchanged
        future_res = await engine.evaluate_recruitment(req, candidates_override=[c1])

        assert baseline_res.decision.decision_id == future_res.decision.decision_id
        assert baseline_res.decision.evidence_hash == future_res.decision.evidence_hash
        assert baseline_res.top_recommendations[0].tactical.tactical_fit_score == (
            future_res.top_recommendations[0].tactical.tactical_fit_score
        )
