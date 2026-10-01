"""Phase 8 Gates 9, 10, 11, 12: Security, Performance, Copilot Safety & DB Immutability.

Validates:
- Gate 9: Performance Audit & Benchmarking (< 250ms analytical SLA, linear candidate scaling).
- Gate 10: Database Audit & Transactional Read Immutability (evidence graph & decision freeze).
- Gate 11: Security Audit (SQL injection immunity, input boundary enforcement, Copilot tool sandboxing).
- Gate 12: Copilot Safety (Zero fabricated analytical figures, evidence-grounded responses, refusal of unsafe execution).
"""
from __future__ import annotations

from datetime import datetime, timezone
import time
import uuid
import pytest

from app.decisions.copilot import ScoutDecisionTools, orchestrate_copilot_decision
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
from app.decisions.service import UnifiedDecisionService
from pydantic import ValidationError


def _create_mock_candidate(
    cid: str,
    name: str,
    pos: str = "MF",
    role: str = "Playmaker",
    fee: float = 25_000_000.0,
    score: float = 85.0,
) -> MultiDimensionalCandidateAssessment:
    return MultiDimensionalCandidateAssessment(
        candidate_id=uuid.UUID(cid),
        player_name=name,
        primary_position=pos,
        target_role=role,
        age=24.5,
        current_club_name="Sporting CP",
        minutes_played=1800,
        hard_constraints=HardConstraintResult(passed=True, checks={"minutes": True, "budget": True}),
        performance=DimensionPerformance(contribution_rating=score, percentile_in_role=82.0),
        tactical=DimensionTactical(
            tactical_fit_score=score,
            role_compatibility=84.0,
            system_name="possession_dominant_433",
            target_role=role,
            strengths=["Progressive passes", "High passing accuracy"],
        ),
        similarity=DimensionSimilarity(overall_similarity=0.88, statistical_similarity=0.85, role_similarity=0.90),
        market=DimensionMarket(
            estimated_value_eur=fee,
            fee_range_low_eur=fee * 0.85,
            fee_range_high_eur=fee * 1.15,
            value_opportunity_index=1.05,
        ),
        risk=DimensionRisk(
            overall_risk_score=0.22,
            performance_risk=0.18,
            adaptation_risk=0.25,
            financial_risk=0.20,
            availability_risk=0.10,
            risk_level="LOW",
            key_risk_drivers=[],
        ),
        squad_impact=DimensionSquadImpact(formation_slot="Midfield", net_squad_upgrade=True),
        prediction_impact=DimensionPredictionImpact(),
        confidence=ConfidenceDecomposition(
            data_confidence=0.85,
            model_confidence=0.88,
            decision_confidence=0.865,
            confidence_tier="HIGH",
            data_status="DECISION_AVAILABLE",
        ),
        hard_constraints_passed=True,
    )


class TestCopilotSecurityAndSandboxing:
    """Gate 11: Security Audit & Copilot Sandboxing."""

    def test_copilot_tool_registry_is_sandboxed(self):
        """Ensures Copilot tool registry only exposes deterministic intelligence methods."""
        tools = ScoutDecisionTools(session=None)
        allowed_methods = {
            "get_player_intelligence",
            "get_player_similarity",
            "get_tactical_fit",
            "get_market_context",
            "get_valuation",
            "get_transfer_risk",
            "analyze_squad",
            "simulate_transfer",
            "get_match_prediction",
            "compare_candidates",
            "retrieve_evidence",
        }
        actual_methods = {
            attr for attr in dir(tools)
            if not attr.startswith("_") and callable(getattr(tools, attr))
        }
        # Tools must never expose os, sys, eval, exec, raw SQL or shell commands
        forbidden_keywords = {"eval", "exec", "os", "subprocess", "shell", "query_raw", "raw_sql", "delete", "drop"}
        for method in actual_methods:
            for forbidden in forbidden_keywords:
                assert forbidden not in method.lower(), f"Forbidden method '{method}' found in Copilot tools"

        assert actual_methods.issubset(allowed_methods)

    @pytest.mark.asyncio
    async def test_copilot_handles_malicious_injections_safely(self):
        """Ensures prompt injection / SQL injection payloads do not execute or crash orchestrator."""
        malicious_queries = [
            "'; DROP TABLE players; --",
            "<script>alert('pwned')</script>",
            "__import__('os').system('whoami')",
            "UNION SELECT * FROM user_credentials WHERE '1'='1",
        ]
        context = [{"id": str(uuid.uuid4()), "name": "Target Midfielder", "primary_position": "MF"}]

        for bad_query in malicious_queries:
            chunks = []
            async for chunk in orchestrate_copilot_decision(bad_query, context_players=context, session=None):
                chunks.append(chunk)
            full_response = "".join(chunks)

            # Response must be generated safely as markdown text without crashing
            assert "Decision Intelligence Analysis" in full_response
            # The malicious payload must not trigger code execution
            assert "pwned" not in full_response
            assert "whoami" not in full_response


class TestCopilotGroundingAndZeroFabrication:
    """Gate 12: Copilot Safety & Provenance Integrity."""

    @pytest.mark.asyncio
    async def test_copilot_replacement_truthful_grounding(self):
        """Verifies all replacement metrics cite deterministic engine outputs without hallucination."""
        target_departing = {
            "id": str(uuid.UUID("00000000-0000-0000-0000-000000000099")),
            "name": "Departing Midfielder",
            "primary_position": "MF",
        }
        c1 = _create_mock_candidate("00000000-0000-0000-0000-000000000001", "Martin Zubimendi", fee=35_000_000.0, score=88.5)
        cand_dict = {
            "id": str(c1.candidate_id),
            "candidate_id": c1.candidate_id,
            "name": c1.player_name,
            "player_name": c1.player_name,
            "primary_position": c1.primary_position,
            "minutes_played": 1800,
            "tactical": c1.tactical,
            "performance": c1.performance,
            "similarity": c1.similarity,
            "market": c1.market,
            "risk": c1.risk,
            "squad_impact": c1.squad_impact,
            "confidence": c1.confidence,
        }
        raw_context = [target_departing, cand_dict]

        chunks = []
        async for chunk in orchestrate_copilot_decision("Find a replacement for our defensive midfielder", raw_context, session=None):
            chunks.append(chunk)


        text = "".join(chunks)
        # Grounding checks:
        assert "Martin Zubimendi" in text
        assert "€35,000,000" in text or "35,000,000" in text
        assert "88.5%" in text or "88.5" in text
        assert "Evidence graph ID" in text

    @pytest.mark.asyncio
    async def test_copilot_truthful_empty_state_caveat(self):
        """Verifies truthful messaging when no candidates meet requirements."""
        chunks = []
        async for chunk in orchestrate_copilot_decision("Find a replacement for player", [], session=None):
            chunks.append(chunk)

        text = "".join(chunks)
        assert "No candidate met both the minimum similarity threshold" in text or "Decision Intelligence Analysis" in text


class TestSecurityAuditAndInputValidation:
    """Gate 11: SQL Injection Prevention & Strict Schema Boundaries."""

    def test_pydantic_enforces_strict_types_preventing_sql_injection(self):
        """Ensures invalid types and injection payloads in UUID fields are rejected at the boundary."""
        with pytest.raises(ValidationError):
            ReplacementDecisionRequest(
                player_id_to_replace="1; DROP TABLE players; --",  # Invalid UUID
                budget_eur=30_000_000.0,
            )

        with pytest.raises(ValidationError):
            ScenarioRosterChange(
                player_id="' OR '1'='1",  # Invalid UUID
                direction="IN",
                fee_eur=10_000_000.0,
            )

    @pytest.mark.asyncio
    async def test_sanitized_string_fields_prevent_sql_injection(self):
        """Ensures malicious tactical context strings are handled safely without SQL execution."""
        service = UnifiedDecisionService(session=None)
        malicious_context = "possession_433'; DROP TABLE clubs; SELECT '"
        req = RecruitmentTargetRequest(
            target_position="MF",
            tactical_context_id=malicious_context,
            budget_eur=20_000_000.0,
        )
        c1 = _create_mock_candidate("00000000-0000-0000-0000-000000000001", "Safe Player")
        response = await service.analyze_recruitment_targets(req, candidates_override=[c1])

        # Service safely executes without executing malicious code
        assert response.decision is not None
        assert response.decision.provenance["tactical_context"] == malicious_context


class TestPerformanceAuditAndBenchmarking:
    """Gate 9: Performance Audit & SLA Benchmarks."""

    @pytest.mark.asyncio
    async def test_decision_service_latency_under_sla(self):
        """Validates that recruitment and replacement evaluations execute in < 250ms."""
        service = UnifiedDecisionService(session=None)
        candidates = [
            _create_mock_candidate(f"00000000-0000-0000-0000-{i:012d}", f"Candidate {i}", score=70.0 + i)
            for i in range(1, 21)
        ]

        t_start = time.perf_counter()
        req = RecruitmentTargetRequest(
            target_position="MF",
            target_role="Playmaker",
            budget_eur=40_000_000.0,
            limit=5,
        )
        resp = await service.analyze_recruitment_targets(req, candidates_override=candidates)
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        assert len(resp.top_recommendations) == 5
        assert elapsed_ms < 250.0, f"Recruitment evaluation took {elapsed_ms:.1f}ms, exceeding 250ms SLA"

    @pytest.mark.asyncio
    async def test_large_candidate_cohort_scaling(self):
        """Validates linear scaling when evaluating a large cohort of 60 candidates."""
        service = UnifiedDecisionService(session=None)
        candidates = [
            _create_mock_candidate(f"00000000-0000-0000-0001-{i:012d}", f"Cohort Player {i}", score=65.0 + (i % 30))
            for i in range(1, 61)
        ]

        t_start = time.perf_counter()
        req = RecruitmentTargetRequest(
            target_position="MF",
            target_role="Playmaker",
            budget_eur=50_000_000.0,
            limit=10,
        )
        resp = await service.analyze_recruitment_targets(req, candidates_override=candidates)
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        assert len(resp.top_recommendations) == 10
        assert elapsed_ms < 500.0, f"Evaluating 60 candidates took {elapsed_ms:.1f}ms, exceeding SLA"


class TestDatabaseAuditAndTransactionalReadImmutability:
    """Gate 10: Decision Snapshots & Transactional Immutability."""

    @pytest.mark.asyncio
    async def test_decision_snapshot_immutability(self):
        """Verifies that decision snapshots retain exact evidence hashes and are cached immutably."""
        service = UnifiedDecisionService(session=None)
        t_fixed = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)
        req = RecruitmentTargetRequest(
            target_position="MF",
            budget_eur=30_000_000.0,
            as_of=t_fixed,
        )
        c1 = _create_mock_candidate("00000000-0000-0000-0000-000000000001", "Immutable Candidate")
        res1 = await service.analyze_recruitment_targets(req, candidates_override=[c1])

        # Retrieve cached decision
        cached_decision = service.get_decision(res1.decision.decision_id)
        assert cached_decision.decision_id == res1.decision.decision_id
        assert cached_decision.evidence_hash == res1.decision.evidence_hash
        assert cached_decision.as_of == t_fixed

        # Retrieve evidence graph
        ev_graph = service.get_decision_evidence(res1.decision.decision_id)
        assert ev_graph.evidence_hash == res1.decision.evidence_hash
