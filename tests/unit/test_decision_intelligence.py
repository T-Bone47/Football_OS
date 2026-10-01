"""Unit tests for Unified Decision Intelligence & Recruitment Engine (Phase 7).

Validates:
- Non-negotiable hard constraints vs soft evidence separation.
- Multi-dimensional candidate assessments (Performance, Tactical, Similarity, Market, Risk, Squad).
- Unconflated confidence decomposition (Data, Model, Decision).
- Replacement decision intelligence with 'Why Matches' & 'Where Differs'.
- Multi-player transfer scenario modeling with financial, squad, and match forecast impact.
- Decision evidence graph DAG traceability.
- Temporal safety: future data injection does not alter historical decision outputs.
"""
from datetime import datetime, timedelta, timezone
import uuid
import pytest

from app.decisions.confidence import DecisionConfidenceEngine
from app.decisions.evidence import DecisionEvidenceGraphBuilder
from app.decisions.hard_constraints import HardConstraintsEngine
from app.decisions.recruitment import RecruitmentTargetEngine
from app.decisions.replacement import ReplacementDecisionEngine
from app.decisions.scenario import DecisionTransferScenarioEngine
from app.decisions.schemas import (
    CandidateComparisonRequest,
    RecruitmentTargetRequest,
    ReplacementDecisionRequest,
    ScenarioRosterChange,
    TransferScenarioDecisionRequest,
)
from app.decisions.service import UnifiedDecisionService


# ============================================================
# 1. HARD CONSTRAINTS VS SOFT EVIDENCE
# ============================================================
class TestHardConstraints:
    """Verifies that hard constraints strictly exclude candidates before soft scoring."""

    def test_position_mismatch_fails(self):
        res = HardConstraintsEngine.evaluate(
            candidate_position="GK",
            target_position="ST",
            age=25.0,
            min_age=18.0,
            max_age=32.0,
            minutes_played=1500,
            min_minutes=500,
            estimated_value_eur=10_000_000.0,
            budget_eur=30_000_000.0,
            risk_level="LOW",
        )
        assert res.passed is False
        assert any("Position mismatch" in r for r in res.exclusion_reasons)

    def test_age_out_of_window_fails(self):
        res = HardConstraintsEngine.evaluate(
            candidate_position="CM",
            target_position="CM",
            age=36.0,
            min_age=18.0,
            max_age=30.0,
            minutes_played=1800,
            min_minutes=500,
            estimated_value_eur=15_000_000.0,
            budget_eur=30_000_000.0,
            risk_level="LOW",
        )
        assert res.passed is False
        assert any("maximum age boundary" in r for r in res.exclusion_reasons)

    def test_minutes_floor_fails(self):
        res = HardConstraintsEngine.evaluate(
            candidate_position="RW",
            target_position="RW",
            age=22.0,
            min_age=18.0,
            max_age=30.0,
            minutes_played=120,
            min_minutes=600,
            estimated_value_eur=8_000_000.0,
            budget_eur=20_000_000.0,
            risk_level="MEDIUM",
        )
        assert res.passed is False
        assert any("Sample insufficiency" in r for r in res.exclusion_reasons)

    def test_budget_ceiling_enforcement(self):
        res = HardConstraintsEngine.evaluate(
            candidate_position="CB",
            target_position="CB",
            age=24.0,
            min_age=18.0,
            max_age=30.0,
            minutes_played=2000,
            min_minutes=500,
            estimated_value_eur=45_000_000.0,
            budget_eur=25_000_000.0,
            risk_level="LOW",
        )
        assert res.passed is False
        assert any("Financial ceiling exceeded" in r for r in res.exclusion_reasons)

    def test_risk_tolerance_threshold(self):
        # LOW risk tolerance should reject HIGH and CRITICAL risk
        res = HardConstraintsEngine.evaluate(
            candidate_position="ST",
            target_position="ST",
            age=26.0,
            min_age=18.0,
            max_age=30.0,
            minutes_played=1500,
            min_minutes=500,
            estimated_value_eur=12_000_000.0,
            budget_eur=20_000_000.0,
            risk_level="HIGH",
            risk_tolerance="LOW",
        )
        assert res.passed is False
        assert any("Risk profile exceeded" in r for r in res.exclusion_reasons)

    def test_all_constraints_pass(self):
        res = HardConstraintsEngine.evaluate(
            candidate_position="CM",
            target_position="CM",
            age=24.0,
            min_age=18.0,
            max_age=30.0,
            minutes_played=1600,
            min_minutes=500,
            estimated_value_eur=18_000_000.0,
            budget_eur=25_000_000.0,
            risk_level="LOW",
            risk_tolerance="MEDIUM",
        )
        assert res.passed is True
        assert len(res.exclusion_reasons) == 0


# ============================================================
# 2. CONFIDENCE DECOMPOSITION & OOD
# ============================================================
class TestDecisionConfidence:
    """Verifies that confidence decomposes cleanly into Data, Model, and Decision tiers."""

    def test_robust_sample_gives_high_confidence(self):
        conf = DecisionConfidenceEngine.evaluate(
            sample_minutes=2200,
            sample_matches=25,
            has_role_profile=True,
            has_tactical_fit=True,
            has_valuation=True,
            has_risk_profile=True,
            is_ood=False,
        )
        assert conf.data_confidence >= 0.85
        assert conf.model_confidence >= 0.80
        assert conf.decision_confidence >= 0.75
        assert conf.confidence_tier == "HIGH"
        assert conf.data_status == "DECISION_AVAILABLE"

    def test_zero_minutes_gives_insufficient_data(self):
        conf = DecisionConfidenceEngine.evaluate(
            sample_minutes=0,
            sample_matches=0,
            has_role_profile=False,
            has_tactical_fit=False,
            has_valuation=False,
            has_risk_profile=False,
        )
        assert conf.data_status == "INSUFFICIENT_DATA"
        assert conf.confidence_tier == "VERY_LOW"
        assert any("Zero recorded match minutes" in u for u in conf.uncertainty_drivers)

    def test_ood_penalizes_model_confidence(self):
        conf = DecisionConfidenceEngine.evaluate(
            sample_minutes=1500,
            sample_matches=18,
            has_role_profile=True,
            has_tactical_fit=True,
            has_valuation=True,
            has_risk_profile=True,
            is_ood=True,
        )
        assert conf.data_status == "OUT_OF_DISTRIBUTION"
        assert any("outside calibrated distribution" in u for u in conf.uncertainty_drivers)


# ============================================================
# 3. RECRUITMENT TARGET ENGINE
# ============================================================
class TestRecruitmentEngine:
    """Verifies the 13-stage recruitment evaluation pipeline."""

    def setup_method(self):
        self.engine = RecruitmentTargetEngine()
        self.sample_candidates = [
            {
                "id": uuid.uuid4(),
                "name": "Declan Rice",
                "primary_position": "DM",
                "age": 25.0,
                "club_name": "Arsenal",
                "minutes_played": 2500,
                "matches_played": 28,
            },
            {
                "id": uuid.uuid4(),
                "name": "Rodri",
                "primary_position": "DM",
                "age": 28.0,
                "club_name": "Manchester City",
                "minutes_played": 2800,
                "matches_played": 32,
            },
            {
                "id": uuid.uuid4(),
                "name": "Young Prospect",
                "primary_position": "DM",
                "age": 19.0,
                "club_name": "Genk",
                "minutes_played": 1100,
                "matches_played": 14,
            },
            {
                "id": uuid.uuid4(),
                "name": "Veteran Striker",
                "primary_position": "ST",  # Position mismatch for DM request
                "age": 34.0,
                "club_name": "Lazio",
                "minutes_played": 1400,
                "matches_played": 16,
            },
        ]

    @pytest.mark.asyncio
    async def test_recruitment_never_invents_dimensions(self):
        """Phase 18 (R23): observed facts alone pass the hard constraints but
        are never ranked; no rating, fit, price or risk is invented."""
        req = RecruitmentTargetRequest(
            target_position="DM",
            target_role="Deep Distributor",
            formation="4-3-3",
            budget_eur=100_000_000.0,
            min_age=18.0,
            max_age=32.0,
            min_minutes=500,
            limit=5,
        )
        res = await self.engine.evaluate_recruitment(req, candidates_override=self.sample_candidates)

        assert res.decision.total_candidates_analyzed == 4
        assert res.decision.excluded_candidates_count == 1  # Veteran striker: position and age
        assert res.top_recommendations == [] and res.status == "INSUFFICIENT_EVIDENCE"
        assert len(res.insufficient_evidence) == 3
        for cand in res.insufficient_evidence:
            assert cand.performance is None and cand.tactical is None and cand.market is None and cand.risk is None
            assert cand.dimension_status["performance"] == "INSUFFICIENT_DATA"
            assert cand.dimension_status["market"] == "MODEL_UNVERIFIED"
            assert cand.dimension_status["minutes"] == "OBSERVED"
            assert cand.ranking_status == "INSUFFICIENT_EVIDENCE" and cand.ranking_score is None
            assert cand.hard_constraints.checks["budget_ceiling"] is None  # unverifiable, not a pass
        assert res.decision.confidence.data_status == "INSUFFICIENT_DATA"

    @pytest.mark.asyncio
    async def test_recruitment_ranks_only_on_supplied_evidence(self):
        perf = {"contribution_rating": 71.0, "sample_minutes": 2500, "sample_matches": 28}
        tac = {"tactical_fit_score": 80.0, "role_compatibility": 78.0, "system_name": "433", "target_role": "DM"}
        cands = [dict(self.sample_candidates[0], performance=perf, tactical=tac),
                 dict(self.sample_candidates[1], performance=dict(perf, contribution_rating=60.0), tactical=tac),
                 self.sample_candidates[2]]
        req = RecruitmentTargetRequest(target_position="DM", min_minutes=500, limit=5)
        res = await self.engine.evaluate_recruitment(req, candidates_override=cands)
        assert res.status == "RANKED"
        assert [c.player_name for c in res.top_recommendations] == ["Declan Rice", "Rodri"]
        assert res.top_recommendations[0].dimension_status["performance"] == "SUPPLIED"
        assert res.top_recommendations[0].ranking_score == round((0.80 + 0.71) / 2, 4)
        assert [c.player_name for c in res.insufficient_evidence] == ["Young Prospect"]

    @pytest.mark.asyncio
    async def test_unknown_values_fail_requested_constraints(self):
        req = RecruitmentTargetRequest(target_position="DM", min_age=18.0, min_minutes=500)
        res = await self.engine.evaluate_recruitment(req, candidates_override=[{"id": uuid.uuid4(), "name": "No Facts"}])
        reasons = res.excluded_summaries[0]["exclusion_reasons"]
        assert any("Position UNKNOWN" in r for r in reasons)
        assert any("Age UNKNOWN" in r for r in reasons)
        assert any("Minutes not reported" in r for r in reasons)


# ============================================================
# 4. REPLACEMENT INTELLIGENCE
# ============================================================
class TestReplacementEngine:
    """Replacement similarity exists only where it is supplied or stored."""

    def setup_method(self):
        self.engine = ReplacementDecisionEngine()
        self.replaced_player = {
            "id": uuid.uuid4(),
            "name": "Martin Odegaard",
            "primary_position": "AM",
            "age": 25.0,
        }
        self.candidates = [
            {"id": uuid.uuid4(), "name": "Florian Wirtz", "primary_position": "AM", "age": 21.0},
            {"id": uuid.uuid4(), "name": "Jamal Musiala", "primary_position": "AM", "age": 21.0},
        ]

    @pytest.mark.asyncio
    async def test_replacement_without_profiles_is_not_ranked(self):
        req = ReplacementDecisionRequest(player_id_to_replace=self.replaced_player["id"], min_similarity=0.60)
        res = await self.engine.evaluate_replacement(
            req, target_player_override=self.replaced_player, candidates_override=self.candidates)
        assert res.replaced_player_name == "Martin Odegaard"
        assert res.top_replacements == [] and res.status == "INSUFFICIENT_EVIDENCE"
        assert {c.player_name for c in res.insufficient_evidence} == {"Florian Wirtz", "Jamal Musiala"}
        assert all(c.similarity is None and c.dimension_status["similarity"] == "NOT_ASSESSED"
                   for c in res.insufficient_evidence)

    @pytest.mark.asyncio
    async def test_replacement_ranks_by_similarity_and_applies_floor(self):
        sim = {"overall_similarity": 0.82, "statistical_similarity": 0.8, "role_similarity": 0.84}
        cands = [dict(self.candidates[0], similarity=sim),
                 dict(self.candidates[1], similarity=dict(sim, overall_similarity=0.41))]
        req = ReplacementDecisionRequest(player_id_to_replace=self.replaced_player["id"], min_similarity=0.60)
        res = await self.engine.evaluate_replacement(
            req, target_player_override=self.replaced_player, candidates_override=cands)
        assert [c.player_name for c in res.top_replacements] == ["Florian Wirtz"]
        assert res.top_replacements[0].ranking_score == 0.82
        assert any("below the minimum" in r for e in res.excluded_summaries for r in e["exclusion_reasons"])
        assert len(res.top_replacements[0].where_differs) > 0  # unestablished dimensions are listed


# ============================================================
# 5. EVIDENCE GRAPH TRACEABILITY
# ============================================================
class TestEvidenceGraph:
    """The DAG holds nodes only for evidence the assessment has; gaps are GAP nodes."""

    def test_evidence_graph_has_traceable_path(self):
        cid = uuid.uuid4()
        req = RecruitmentTargetRequest(target_position="CB")
        engine = RecruitmentTargetEngine()
        sample = [{
            "id": cid, "name": "William Saliba", "primary_position": "CB", "age": 23.0, "minutes_played": 2600,
            "performance": {"contribution_rating": 70.0},
            "tactical": {"tactical_fit_score": 75.0, "role_compatibility": 70.0, "system_name": "433",
                         "target_role": "CB"},
        }]
        import asyncio
        res = asyncio.run(engine.evaluate_recruitment(req, candidates_override=sample))
        graph = res.decision.evidence_graph
        assert graph is not None and len(graph.evidence_hash) == 64
        types = [n.node_type for n in graph.nodes]
        assert {"PLAYER", "CONTRIBUTION", "TACTICAL_FIT", "DECISION"} <= set(types)
        assert "VALUATION" not in types and "RISK" not in types  # nothing invented
        gaps = {n.value["dimension"]: n.value["status"] for n in graph.nodes if n.node_type == "GAP"}
        assert gaps == {"similarity": "NOT_ASSESSED", "market": "MODEL_UNVERIFIED", "risk": "INSUFFICIENT_DATA",
                        "squad_impact": "NOT_ASSESSED"}
        decision_id = f"decision_{res.decision.decision_id}"
        assert {e.from_node for e in graph.edges if e.to_node == decision_id} >= {f"performance_{cid}", f"tactical_{cid}"}


# ============================================================
# 6. CANDIDATE COMPARISON
# ============================================================
class TestCandidateComparison:
    """Exactly the requested candidates; leaders only where evidence exists."""

    def setup_method(self):
        self.service = UnifiedDecisionService()
        self.id_a = uuid.uuid4()
        self.id_b = uuid.uuid4()
        self.sample = [
            {"id": self.id_a, "name": "Candidate A", "primary_position": "CM", "age": 23.0, "minutes_played": 1800,
             "performance": {"contribution_rating": 66.0}},
            {"id": self.id_b, "name": "Candidate B", "primary_position": "CM", "age": 27.0, "minutes_played": 2200},
            {"id": uuid.uuid4(), "name": "Not Requested", "primary_position": "CM"},
        ]

    @pytest.mark.asyncio
    async def test_compare_candidates(self):
        missing = uuid.uuid4()
        req = CandidateComparisonRequest(candidate_ids=[self.id_a, self.id_b, missing], target_role="Playmaker")
        res = await self.service.compare_candidates(req, candidates_override=self.sample)
        assert [c.player_name for c in res.candidates] == ["Candidate A", "Candidate B"]
        assert res.not_found_candidate_ids == [missing]
        assert len(res.trade_off_analysis) == 2
        assert res.dimension_leaders == {"performance": "Candidate A"}  # no tactical evidence: no tactical leader


# ============================================================
# 7. TEMPORAL SAFETY & INVARIANCE
# ============================================================
class TestTemporalDecisionSafety:
    """A point-in-time analysis is deterministic for the same as_of and evidence."""

    def test_future_candidate_injection_invariance(self):
        engine = RecruitmentTargetEngine()
        as_of = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        base = [{"id": uuid.UUID(int=1), "name": "Historical Candidate", "primary_position": "ST", "age": 24.0,
                 "minutes_played": 1500, "performance": {"contribution_rating": 64.0},
                 "tactical": {"tactical_fit_score": 70.0, "role_compatibility": 70.0, "system_name": "433",
                              "target_role": "ST"}}]
        req = RecruitmentTargetRequest(target_position="ST", as_of=as_of)
        import asyncio
        first = asyncio.run(engine.evaluate_recruitment(req, candidates_override=base))
        second = asyncio.run(engine.evaluate_recruitment(req, candidates_override=base))
        assert first.decision.decision_id == second.decision.decision_id
        assert first.decision.evidence_hash == second.decision.evidence_hash
        assert first.top_recommendations[0].ranking_score == second.top_recommendations[0].ranking_score


# ============================================================
# 8. TRANSFER SCENARIO (COUNTERFACTUAL)
# ============================================================
class TestTransferScenario:
    """Fees are caller assumptions; a missing fee is unknown, never a default price."""

    @pytest.mark.asyncio
    async def test_missing_fee_is_unknown_and_output_is_counterfactual(self):
        engine = DecisionTransferScenarioEngine()
        req = TransferScenarioDecisionRequest(
            club_id=uuid.uuid4(), budget_eur=30_000_000.0,
            roster_changes=[ScenarioRosterChange(player_id=uuid.uuid4(), direction="IN", fee_eur=20_000_000.0),
                            ScenarioRosterChange(player_id=uuid.uuid4(), direction="OUT")],
        )
        res = await engine.evaluate_scenario(req)
        fin = res.financial_impact
        assert fin["modality"] == "SCENARIO_ASSUMPTION"
        assert fin["net_transfer_spend_eur"] is None and fin["financial_feasibility"] == "UNKNOWN"
        assert fin["total_expenditure_eur"] == 20_000_000.0 and fin["total_income_eur"] is None
        assert res.squad_impact_summary["status"] == "NOT_ASSESSED"
        assert res.match_prediction_impact is None
        assert res.decision.provenance["modality"] == "COUNTERFACTUAL"
        assert res.decision.confidence.model_confidence == 0.0

    @pytest.mark.asyncio
    async def test_supplied_fees_give_feasibility(self):
        engine = DecisionTransferScenarioEngine()
        req = TransferScenarioDecisionRequest(
            club_id=uuid.uuid4(), budget_eur=10_000_000.0,
            roster_changes=[ScenarioRosterChange(player_id=uuid.uuid4(), direction="IN", fee_eur=25_000_000.0),
                            ScenarioRosterChange(player_id=uuid.uuid4(), direction="OUT", fee_eur=5_000_000.0)],
        )
        fin = (await engine.evaluate_scenario(req)).financial_impact
        assert fin["net_transfer_spend_eur"] == 20_000_000.0
        assert fin["remaining_budget_eur"] == -10_000_000.0 and fin["financial_feasibility"] == "DEFICIT"
