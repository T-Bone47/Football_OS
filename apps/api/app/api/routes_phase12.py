"""Phase 12 — Continuous Learning & Advanced Recruitment Intelligence API Routes (§26).

Exposes REST endpoints for:
  - Emerging player discovery & breakout detection (§9, §10)
  - Longitudinal player trajectories V2 (§8)
  - Tactical role transition tracking (§11)
  - Market inefficiency & value gap detection (§12)
  - Immutable decision freshness assessments (§4)
  - Champion vs Challenger model framework (§7, §18, §19)
  - Governed continuous model retraining triggers (§5, §6)
  - Continuous data impact propagation events (§3)
  - Versioned benchmark player profiles (§14)
  - Multi-mode recruitment candidate discovery (§13, §15)
  - Post-decision & post-transfer retrospective evaluation (§16, §17)
  - Global player evidence graph inspection (§22)
  - Scout Copilot V2 deterministic query dispatch (§23)
  - Factual operational alerts V2 (§24)
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.phase12 import (
    CandidateDiscoveryMode,
    DecisionFreshnessState,
    MarketOpportunityState,
    RetrainRecommendation,
)
from app.phase12.alerts_v2 import AlertCategoryV2, alerts_manager_v2
from app.phase12.benchmarks import benchmark_registry
from app.phase12.challenger_framework import challenger_framework
from app.phase12.copilot_v2 import copilot_v2_dispatcher
from app.phase12.data_impact import data_impact_engine
from app.phase12.decision_staleness import decision_staleness_engine
from app.phase12.emerging_players import emerging_player_engine
from app.phase12.evidence_graph import player_evidence_graph_builder
from app.phase12.learning_loop import learning_pipeline
from app.phase12.market_inefficiency import market_inefficiency_engine
from app.phase12.player_trajectories import player_trajectory_engine
from app.phase12.post_decision_feedback import post_decision_feedback_engine
from app.phase12.recruitment_discovery import recruitment_discovery_engine
from app.phase12.retraining_triggers import retraining_trigger_engine
from app.phase12.role_transitions import role_transition_engine

router = APIRouter(prefix="/api/phase12", tags=["Phase 12 Continuous Intelligence Operations"])


# ── Schemas ──────────────────────────────────────────────────────────

class BenchmarkCreateRequest(BaseModel):
    name: str = "2026/27 Elite Ball Playing CB"
    version: str = "1.0.0"
    position: str = "CB"
    target_role: str = "Ball Playing Defender"
    formation: str = "4-3-3"
    dimension_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "progression": 0.25,
            "passing": 0.20,
            "defending": 0.20,
            "carrying": 0.15,
            "aerial": 0.10,
            "retention": 0.10,
        }
    )
    source_reference_players: list[str] = Field(default_factory=lambda: ["William Saliba", "John Stones"])
    competition_scope: list[str] = Field(default_factory=lambda: ["GB-PL", "ES-L1", "IT-SA", "DE-BL", "FR-L1"])
    created_by: str = "Scout"


class CandidateDiscoveryRequest(BaseModel):
    target_position: str = "CB"
    target_role: str = "Ball Playing Defender"
    mode: str = "EMERGING"  # ROLE_SIMILAR, CONTRIBUTION_SIMILAR, TACTICAL_SIMILAR, MARKET_VALUE_GAP, EMERGING, REPLACEMENT, SCENARIO_CONSTRAINED
    max_age: int = 27
    max_budget_eur: float = 60_000_000.0


class CopilotQueryRequest(BaseModel):
    query: str


class PromoteChallengerRequest(BaseModel):
    job_id: str
    approver: str = "Lead MLOps Engineer"


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/emerging")
def list_emerging_players(status: str | None = None) -> list[dict[str, Any]]:
    """Lists detected emerging players and breakout candidates."""
    opps = emerging_player_engine.list_opportunities(status=status)
    return [o.to_dict() for o in opps]


@router.get("/players/{player_id}/trajectory")
def get_player_trajectory(player_id: str) -> dict[str, Any]:
    """Retrieves longitudinal player trajectory profile (OBSERVED/MODELLED/PROJECTED)."""
    prof = player_trajectory_engine.get_profile(player_id)
    if not prof:
        raise HTTPException(status_code=404, detail=f"Player trajectory for {player_id} not found.")
    return prof.to_dict()


@router.get("/role-transitions")
def list_role_transitions(player_id: str | None = None) -> list[dict[str, Any]]:
    """Lists verified tactical role transitions."""
    transitions = role_transition_engine.list_transitions(player_id=player_id)
    return [t.to_dict() for t in transitions]


@router.get("/market/opportunities")
def list_market_opportunities(state: str | None = None) -> list[dict[str, Any]]:
    """Lists market value gap opportunities comparing modelled valuations to market references."""
    st = MarketOpportunityState(state) if state else None
    signals = market_inefficiency_engine.list_signals(state=st)
    return [s.to_dict() for s in signals]


@router.get("/decisions/freshness")
def list_decision_freshness() -> list[dict[str, Any]]:
    """Audits freshness of immutable historical decision records."""
    assessments = decision_staleness_engine.list_assessments()
    return [a.to_dict() for a in assessments]


@router.get("/models/challengers")
def list_challenger_comparisons() -> list[dict[str, Any]]:
    """Lists Champion vs Challenger comparative evaluations."""
    comparisons = challenger_framework.list_comparisons()
    return [c.to_dict() for c in comparisons]


@router.get("/models/retraining")
def list_retraining_recommendations() -> list[dict[str, Any]]:
    """Lists deterministic retraining recommendations."""
    recs = retraining_trigger_engine.list_recommendations()
    return [r.to_dict() for r in recs]


@router.get("/impact/events")
def list_data_impact_events() -> list[dict[str, Any]]:
    """Lists continuous data impact propagation events."""
    events = data_impact_engine.list_events()
    return [e.to_dict() for e in events]


@router.get("/benchmarks")
def list_benchmarks() -> list[dict[str, Any]]:
    """Lists versioned benchmark recruitment profiles."""
    profiles = benchmark_registry.list_benchmarks()
    return [p.to_dict() for p in profiles]


@router.post("/benchmarks")
def create_benchmark(req: BenchmarkCreateRequest) -> dict[str, Any]:
    """Creates a new versioned benchmark profile."""
    profile = benchmark_registry.create_benchmark(
        name=req.name,
        position=req.position,
        target_role=req.target_role,
        formation=req.formation,
        dimension_weights=req.dimension_weights,
        source_reference_players=req.source_reference_players,
        competition_scope=req.competition_scope,
        version=req.version,
        created_by=req.created_by,
    )
    return profile.to_dict()


@router.post("/recruitment/discover")
def discover_candidates(req: CandidateDiscoveryRequest) -> list[dict[str, Any]]:
    """Discovers candidates using specified discovery mode with position & budget gating."""
    try:
        mode_enum = CandidateDiscoveryMode(req.mode)
    except ValueError:
        mode_enum = CandidateDiscoveryMode.ROLE_SIMILAR

    candidates = recruitment_discovery_engine.discover_candidates(
        target_position=req.target_position,
        target_role=req.target_role,
        mode=mode_enum,
        max_age=req.max_age,
        max_budget_eur=req.max_budget_eur,
    )
    return [c.to_dict() for c in candidates]


@router.get("/post-decision/feedback")
def list_post_decision_feedback() -> list[dict[str, Any]]:
    """Lists post-decision and post-transfer realization feedback."""
    records = post_decision_feedback_engine.list_feedbacks()
    return [r.to_dict() for r in records]


@router.get("/players/{player_id}/evidence-graph")
def get_player_evidence_graph(player_id: str, player_name: str = "Player") -> dict[str, Any]:
    """Generates the end-to-end 10-tier Player Evidence Graph."""
    graph = player_evidence_graph_builder.build_graph(player_id=player_id, player_name=player_name)
    return graph.to_dict()


@router.post("/copilot/query")
def copilot_v2_query(req: CopilotQueryRequest) -> dict[str, Any]:
    """Dispatches a natural language continuous intelligence query to deterministic tools."""
    return copilot_v2_dispatcher.dispatch(req.query)


@router.get("/alerts")
def list_alerts_v2(category: str | None = None) -> list[dict[str, Any]]:
    """Lists active Phase 12 operational alerts."""
    cat = AlertCategoryV2(category) if category else None
    alerts = alerts_manager_v2.list_alerts(category=cat)
    return [a.to_dict() for a in alerts]


@router.get("/learning/jobs")
def list_learning_jobs() -> list[dict[str, Any]]:
    """Lists continuous model learning pipeline runs."""
    jobs = learning_pipeline.list_jobs()
    return [j.to_dict() for j in jobs]


@router.post("/learning/promote")
def promote_challenger(req: PromoteChallengerRequest) -> dict[str, Any]:
    """Promotes an audited challenger model to production."""
    try:
        job = learning_pipeline.promote_challenger(job_id=req.job_id, approver=req.approver)
        return job.to_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
