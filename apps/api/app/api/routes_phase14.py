"""Phase 14 — Outcome-Aware Decision Intelligence REST API Routes (§23).

Exposes versioned REST endpoints under /api/v1/outcomes:
  - GET  /api/v1/outcomes/decisions
  - GET  /api/v1/outcomes/decisions/{decision_id}
  - GET  /api/v1/outcomes/decisions/{decision_id}/evaluation
  - POST /api/v1/outcomes/evaluate
  - GET  /api/v1/outcomes/ledger
  - GET  /api/v1/outcomes/transfers
  - GET  /api/v1/outcomes/tactical
  - GET  /api/v1/outcomes/scenarios
  - GET  /api/v1/outcomes/models/{model_id}/calibration
  - GET  /api/v1/outcomes/models/{model_id}/subgroups
  - GET  /api/v1/outcomes/learning-signals
  - GET  /api/v1/outcomes/freshness
  - GET  /api/v1/outcomes/research
  - POST /api/v1/outcomes/research
  - GET  /api/v1/outcomes/evidence/{decision_id}
  - POST /api/v1/outcomes/copilot

Strict adherence to Pydantic contracts and non-causal epistemic policies.
Zero business logic inside router functions.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.phase14 import OutcomeType
from app.phase14.copilot_v4 import copilot_v4_dispatcher
from app.phase14.decision_freshness_v2 import decision_freshness_v2_engine
from app.phase14.decision_realization import decision_realization_evaluator
from app.phase14.decision_record_v3 import decision_record_store_v3
from app.phase14.evidence_graph_v3 import evidence_graph_v3_builder
from app.phase14.learning_loop import decision_learning_loop_engine
from app.phase14.outcome_ledger import outcome_ledger
from app.phase14.prediction_calibration_feedback import prediction_calibration_feedback_engine
from app.phase14.process_quality import process_quality_engine
from app.phase14.research_mode import research_workspace_engine
from app.phase14.subgroup_monitoring import subgroup_monitoring_engine
from app.phase14.tactical_realization import tactical_realization_engine

router = APIRouter(prefix="/api/v1/outcomes", tags=["Phase 14 Outcome Intelligence"])


# ── Pydantic Request Schemas ──────────────────────────────────────────

class EvaluateDecisionRequest(BaseModel):
    decision_id: str
    scenario_id: str
    subject_entity_id: str
    subject_name: str
    expectations: list[dict[str, Any]]
    evaluation_window: str = "POST_DECISION_WINDOW"
    assumptions: list[str] = []


class CreateResearchRequest(BaseModel):
    topic: str
    hypothesis: str
    items: list[dict[str, Any]]
    created_by: str = "analyst_research_lead"


class CopilotOutcomeQueryRequest(BaseModel):
    query: str
    decision_id: str | None = None
    scenario_id: str | None = None


# ── Router Endpoints ──────────────────────────────────────────────────

@router.get("/decisions")
def list_decisions_v3() -> list[dict[str, Any]]:
    """Lists all Decision Record V3 entries with historical and retrospective sections."""
    records = decision_record_store_v3.list_records()
    return [r.to_dict() for r in records]


@router.get("/decisions/{decision_id}")
def get_decision_v3(decision_id: str) -> dict[str, Any]:
    """Fetches a single Decision Record V3 entry."""
    rec = decision_record_store_v3.get_record(decision_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found in V3 store.")
    return rec.to_dict()


@router.get("/decisions/{decision_id}/evaluation")
def get_decision_evaluation(decision_id: str) -> dict[str, Any]:
    """Fetches retrospective realization evaluation for a decision."""
    eval_rec = decision_realization_evaluator.get_evaluation(decision_id)
    if not eval_rec:
        raise HTTPException(status_code=404, detail=f"No realization evaluation found for {decision_id}.")
    audit = process_quality_engine.get_process_audit(decision_id)
    diag = process_quality_engine.get_divergence_diagnostic(decision_id)
    res = eval_rec.to_dict()
    res["process_quality_audit"] = audit.to_dict() if audit else None
    res["divergence_diagnostic"] = diag.to_dict() if diag else None
    return res


@router.post("/evaluate")
def evaluate_decision(req: EvaluateDecisionRequest) -> dict[str, Any]:
    """Evaluates decision-time expectations vs real-world outcome observations."""
    evaluation = decision_realization_evaluator.evaluate_decision(
        decision_id=req.decision_id,
        scenario_id=req.scenario_id,
        subject_entity_id=req.subject_entity_id,
        subject_name=req.subject_name,
        expectations=req.expectations,
        evaluation_window=req.evaluation_window,
        assumptions=req.assumptions,
    )
    # Link to Decision Record V3
    decision_record_store_v3.link_realization_evaluation(
        decision_id=req.decision_id,
        evaluation_id=evaluation.evaluation_id,
        overall_alignment=evaluation.overall_alignment.value,
        divergence_metrics=evaluation.primary_divergence_metrics,
        learning_signal_ids=[],
    )
    return evaluation.to_dict()


@router.get("/ledger")
def list_outcome_ledger(
    decision_id: str | None = None,
    scenario_id: str | None = None,
    player_id: str | None = None,
    club_id: str | None = None,
    competition_id: str | None = None,
    outcome_type: str | None = None,
) -> list[dict[str, Any]]:
    """Queries immutable Outcome Ledger entries."""
    ot = OutcomeType(outcome_type) if outcome_type and outcome_type in OutcomeType.__members__ else None
    outcomes = outcome_ledger.list_outcomes(
        decision_id=decision_id,
        scenario_id=scenario_id,
        player_id=player_id,
        club_id=club_id,
        competition_id=competition_id,
        outcome_type=ot,
    )
    return [o.to_dict() for o in outcomes]


@router.get("/transfers")
def list_transfer_realizations() -> list[dict[str, Any]]:
    """Fetches completed transfer realizations."""
    transfers = outcome_ledger.list_outcomes(outcome_type=OutcomeType.TRANSFER_REALIZATION)
    return [t.to_dict() for t in transfers]


@router.get("/tactical")
def list_tactical_realizations() -> list[dict[str, Any]]:
    """Fetches tactical realization audits."""
    reports = list(tactical_realization_engine._tactical_reports.values())
    return [r.to_dict() for r in reports]


@router.get("/scenarios")
def list_scenario_realizations() -> list[dict[str, Any]]:
    """Fetches scenario lifecycle realization statuses."""
    scenarios = tactical_realization_engine.list_scenario_realizations()
    return [s.to_dict() for s in scenarios]


@router.get("/models/{model_id}/calibration")
def get_model_calibration(
    model_id: str,
    window_size: int = Query(default=30, ge=10, le=100),
    competition_id: str = "premier_league",
) -> dict[str, Any]:
    """Computes rolling calibration and scoring rules for a model."""
    rep = prediction_calibration_feedback_engine.compute_window_calibration(
        window_size=window_size,
        competition_id=competition_id,
        model_version=model_id,
    )
    return rep.to_dict()


@router.get("/models/{model_id}/subgroups")
def get_model_subgroups(model_id: str) -> dict[str, Any]:
    """Fetches contextual subgroup performance slices."""
    rep = subgroup_monitoring_engine.get_contextual_report(model_id)
    if not rep:
        rep = subgroup_monitoring_engine.generate_contextual_report(model_id=model_id)
    return rep.to_dict()


@router.get("/learning-signals")
def list_learning_signals() -> dict[str, Any]:
    """Lists institutional learning signals and challenger evaluations."""
    signals = decision_learning_loop_engine.list_signals()
    patterns = decision_learning_loop_engine.list_patterns()
    challengers = decision_learning_loop_engine.list_challenger_evaluations()
    return {
        "learning_signals": [s.to_dict() for s in signals],
        "pattern_reports": [p.to_dict() for p in patterns],
        "challenger_evaluations": [c.to_dict() for c in challengers],
    }


@router.get("/freshness")
def list_decision_freshness() -> list[dict[str, Any]]:
    """Lists decision freshness assessments across active decisions."""
    assessments = decision_freshness_v2_engine.list_assessments()
    return [a.to_dict() for a in assessments]


@router.get("/research")
def list_research_dossiers() -> list[dict[str, Any]]:
    """Lists all governed research dossiers."""
    dossiers = research_workspace_engine.list_dossiers()
    return [d.to_dict() for d in dossiers]


@router.post("/research")
def create_research_dossier(req: CreateResearchRequest) -> dict[str, Any]:
    """Creates a new research dossier with explicit epistemic tagging."""
    dossier = research_workspace_engine.create_research_dossier(
        topic=req.topic,
        hypothesis=req.hypothesis,
        items=req.items,
        created_by=req.created_by,
    )
    return dossier.to_dict()


@router.get("/evidence/{decision_id}")
def get_evidence_graph_v3(decision_id: str) -> dict[str, Any]:
    """Fetches or builds the Evidence Graph V3 lineage for a decision."""
    graph = evidence_graph_v3_builder.get_graph(decision_id)
    if not graph:
        graph = evidence_graph_v3_builder.build_decision_graph(decision_id, "scen_default")
    return graph.to_dict()


@router.post("/copilot")
def query_copilot_v4(req: CopilotOutcomeQueryRequest) -> dict[str, Any]:
    """Deterministic Scout Copilot V4 outcome-aware query dispatcher."""
    ctx = {
        "decision_id": req.decision_id or "dec_rec_timber_2023",
        "scenario_id": req.scenario_id or "scen_timber_sign",
    }
    return copilot_v4_dispatcher.dispatch(query=req.query, context=ctx)
