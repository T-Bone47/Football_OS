"""Phase 13 — Decision Intelligence 2.0 API Routes (§28).

Exposes REST endpoints for the Decision Lab:
  - GET  /api/v1/decision-lab/squad/{club_id}
  - GET  /api/v1/decision-lab/tactical/{club_id}
  - GET  /api/v1/decision-lab/depth/{club_id}
  - POST /api/v1/decision-lab/scenarios
  - GET  /api/v1/decision-lab/scenarios
  - GET  /api/v1/decision-lab/scenarios/{scenario_id}
  - POST /api/v1/decision-lab/scenarios/compare
  - POST /api/v1/decision-lab/scenarios/simulate
  - POST /api/v1/decision-lab/sensitivity
  - POST /api/v1/decision-lab/robustness
  - POST /api/v1/decision-lab/budget
  - GET  /api/v1/decision-lab/evidence/{scenario_id}
  - POST /api/v1/decision-lab/finalize
  - GET  /api/v1/decision-lab/decisions
  - POST /api/v1/decision-lab/follow-up
  - POST /api/v1/decision-lab/copilot

Strict adherence to Pydantic contracts and non-causal epistemic policies.
Zero business logic inside router functions.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.phase13.budget_depth_simulator import budget_depth_simulator
from app.phase13.copilot_v3 import copilot_v3_dispatcher
from app.phase13.decision_record_v2 import (
    DecisionRecordV2,
    ScenarioAlternativeSummary,
    decision_record_store_v2,
)
from app.phase13.multi_transfer_scenario import (
    MultiTransferScenario,
    ScenarioMovement,
    multi_transfer_scenario_engine,
)
from app.phase13.player_replacement import player_replacement_simulator
from app.phase13.scenario_graph import scenario_graph_builder
from app.phase13.sensitivity_robustness import (
    ScenarioRobustnessAnalyzer,
    ScenarioSensitivityAnalyzer,
)
from app.phase13.squad_baseline import squad_baseline_registry
from app.phase13.squad_construction import squad_construction_engine_v2
from app.phase13.tactical_simulator import tactical_system_simulator

router = APIRouter(prefix="/api/v1/decision-lab", tags=["Phase 13 Decision Intelligence 2.0"])

sensitivity_analyzer = ScenarioSensitivityAnalyzer()
robustness_analyzer = ScenarioRobustnessAnalyzer()


# ── Pydantic Request / Response Schemas ─────────────────────────────────

class MovementInput(BaseModel):
    action: str = Field(..., description="BUY, SELL, RETAIN, PROMOTE_ACADEMY")
    player_id: str
    player_name: str
    position: str
    fee_eur: float = 0.0
    weekly_wage_eur: float = 0.0
    tactical_role: str = ""


class CreateScenarioRequest(BaseModel):
    name: str = "Scenario: Tactical Replacement"
    club_id: str = "arsenal_fc"
    scenario_type: str = "SELL_BUY"
    movements: list[MovementInput] = []
    assumptions: list[str] = []


class CompareScenariosRequest(BaseModel):
    scenario_ids: list[str] = Field(..., min_length=2)
    club_id: str = "arsenal_fc"


class SimulateScenarioRequest(BaseModel):
    scenario_id: str | None = None
    club_id: str = "arsenal_fc"
    movements: list[MovementInput] = []
    assumptions: list[str] = []
    hypothetical_formation: str | None = None


class SensitivityRequest(BaseModel):
    scenario_id: str
    club_id: str = "arsenal_fc"
    net_spend_eur: float = 20_000_000.0
    wage_delta_weekly: float = -80_000.0
    tactical_fit: float = 88.4


class RobustnessRequest(BaseModel):
    scenario_id: str
    scenario_name: str
    club_id: str = "arsenal_fc"
    net_spend_eur: float = 20_000_000.0
    wage_bill_delta: float = -80_000.0
    tactical_fit_delta: float = +2.2
    squad_depth_delta: float = +1.5


class BudgetParetoRequest(BaseModel):
    club_id: str = "arsenal_fc"
    formation: str = "4-3-3"
    budget_ceiling_eur: float = 65_000_000.0


class FinalizeDecisionRequest(BaseModel):
    project_id: str
    project_name: str
    club_id: str = "arsenal_fc"
    chosen_scenario_id: str
    chosen_scenario_name: str
    candidate_set: list[dict[str, Any]] = []
    alternatives_considered: list[dict[str, Any]] = []
    scenario_assumptions: list[str] = []
    constraints: dict[str, Any] = {}
    human_annotations: str = ""
    signed_by: str = "Head of Recruitment"


class FollowUpRequest(BaseModel):
    decision_id: str
    realized_fee_eur: float
    realized_wage_eur: float
    realized_minutes: float
    observed_role: str
    observed_availability_pct: float
    observed_contribution: float


class CopilotQueryRequest(BaseModel):
    query: str
    club_id: str = "arsenal_fc"


# ── Endpoint Implementations ───────────────────────────────────────────

@router.get("/squad/{club_id}")
def get_squad_baseline(club_id: str) -> dict[str, Any]:
    """Returns verified squad roster, tactical identity, and financial state (§4)."""
    try:
        baseline = squad_baseline_registry.get_baseline(club_id)
    except KeyError:
        baseline = None
    # get_baseline returns None for an unknown club; this used to surface as a 500.
    if baseline is None:
        raise HTTPException(status_code=404, detail=f"Club baseline '{club_id}' not found.")
    return baseline.to_dict()


@router.get("/tactical/{club_id}")
def evaluate_tactical_system(
    club_id: str,
    formation: str = Query("4-3-3", description="Formation to simulate (e.g., 4-3-3, 3-4-2-1)"),
) -> dict[str, Any]:
    """Evaluates formation compatibility, role coverage, and tactical diagnostics (§8)."""
    try:
        evaluation = tactical_system_simulator.evaluate_formation(club_id, formation)
        return evaluation.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/depth/{club_id}")
def simulate_squad_depth(
    club_id: str,
    congestion: str = Query("DOMESTIC_LEAGUE", description="DOMESTIC_LEAGUE, DOMESTIC_PLUS_EUROPE, SEVERE_CONGESTION"),
) -> dict[str, Any]:
    """Simulates squad depth state and rotation vulnerabilities under fixture schedules (§11, §12)."""
    return budget_depth_simulator.simulate_depth_stress(club_id=club_id, congestion_mode=congestion).to_dict()


@router.post("/scenarios")
def create_scenario(req: CreateScenarioRequest) -> dict[str, Any]:
    """Registers and executes a new multi-transfer simulation scenario (§6, §16)."""
    movements = [
        ScenarioMovement(
            action=m.action,
            player_id=m.player_id,
            player_name=m.player_name,
            position=m.position,
            fee_eur=m.fee_eur,
            weekly_wage_eur=m.weekly_wage_eur,
            tactical_role=m.tactical_role,
        )
        for m in req.movements
    ]
    scen = multi_transfer_scenario_engine.simulate_scenario(
        name=req.name,
        club_id=req.club_id,
        scenario_type=req.scenario_type,
        movements=movements,
        assumptions=req.assumptions,
    )
    return scen.to_dict()


@router.get("/scenarios")
def list_scenarios(club_id: str = Query("arsenal_fc")) -> list[dict[str, Any]]:
    """Lists all available scenarios for the club."""
    scens = multi_transfer_scenario_engine.list_scenarios(club_id=club_id)
    return [s.to_dict() for s in scens]


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str) -> dict[str, Any]:
    """Retrieves a specific scenario by ID."""
    scen = multi_transfer_scenario_engine.get_scenario(scenario_id)
    if not scen:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")
    return scen.to_dict()


@router.post("/scenarios/compare")
def compare_scenarios(req: CompareScenariosRequest) -> dict[str, Any]:
    """Performs side-by-side Pareto trade-off comparison across alternatives (§14, §19)."""
    comp = multi_transfer_scenario_engine.compare_scenarios(
        scenario_ids=req.scenario_ids,
        club_id=req.club_id,
    )
    return comp.to_dict()


@router.post("/scenarios/simulate")
def simulate_scenario(req: SimulateScenarioRequest) -> dict[str, Any]:
    """Evaluates instant on-the-fly scenario adjustments without mutating store (§6, §15)."""
    movements = [
        ScenarioMovement(
            action=m.action,
            player_id=m.player_id,
            player_name=m.player_name,
            position=m.position,
            fee_eur=m.fee_eur,
            weekly_wage_eur=m.weekly_wage_eur,
            tactical_role=m.tactical_role,
        )
        for m in req.movements
    ]
    scen = multi_transfer_scenario_engine.simulate_scenario(
        name="On-The-Fly Simulation",
        club_id=req.club_id,
        scenario_type="CUSTOM",
        movements=movements,
        assumptions=req.assumptions,
    )
    return scen.to_dict()


@router.post("/sensitivity")
def evaluate_sensitivity(req: SensitivityRequest) -> dict[str, Any]:
    """Calculates low/base/high assumption bounds for a scenario (§20)."""
    profile = sensitivity_analyzer.evaluate_sensitivity(
        scenario_id=req.scenario_id,
        club_id=req.club_id,
        base_net_spend_eur=req.net_spend_eur,
        base_wage_delta_weekly=req.wage_delta_weekly,
        base_tactical_fit=req.tactical_fit,
    )
    return profile.to_dict()


@router.post("/robustness")
def evaluate_robustness(req: RobustnessRequest) -> dict[str, Any]:
    """Classifies scenario resilience under compounding perturbations (§21)."""
    report = robustness_analyzer.test_robustness(
        scenario_id=req.scenario_id,
        scenario_name=req.scenario_name,
        club_id=req.club_id,
        net_spend_eur=req.net_spend_eur,
        wage_bill_delta=req.wage_bill_delta,
        tactical_fit_delta=req.tactical_fit_delta,
        squad_depth_delta=req.squad_depth_delta,
    )
    return report.to_dict()


@router.post("/budget")
def evaluate_budget_frontier(req: BudgetParetoRequest) -> list[dict[str, Any]]:
    """Calculates the Pareto decision frontier across squad strategies (§5, §13, §14)."""
    frontier = squad_construction_engine_v2.generate_pareto_frontier(
        club_id=req.club_id,
        formation=req.formation,
        budget_ceiling_eur=req.budget_ceiling_eur,
    )
    return [sol.to_dict() for sol in frontier]


@router.get("/evidence/{scenario_id}")
def get_scenario_evidence(scenario_id: str, club_id: str = Query("arsenal_fc")) -> dict[str, Any]:
    """Generates the unified 12-stage cryptographic Evidence Graph V2 (§3, §22)."""
    scen = multi_transfer_scenario_engine.get_scenario(scenario_id)
    movements = scen.movements if scen else []
    assumptions = scen.assumptions if scen else []
    graph = scenario_graph_builder.build_graph(
        club_id=club_id,
        scenario_id=scenario_id,
        movements=movements,
        assumptions=assumptions,
    )
    return graph.to_dict()


@router.post("/finalize")
def finalize_decision(req: FinalizeDecisionRequest) -> dict[str, Any]:
    """Permanently commits an immutable Decision Record V2 (§23)."""
    alternatives = [
        ScenarioAlternativeSummary(
            scenario_id=a.get("scenario_id", ""),
            name=a.get("name", ""),
            net_spend_eur=float(a.get("net_spend_eur", 0.0)),
            tactical_fit_delta=float(a.get("tactical_fit_delta", 0.0)),
            squad_depth_delta=float(a.get("squad_depth_delta", 0.0)),
            rejection_rationale=a.get("rejection_rationale", "Alternative not selected."),
        )
        for a in req.alternatives_considered
    ]
    record = DecisionRecordV2(
        project_id=req.project_id,
        project_name=req.project_name,
        club_id=req.club_id,
        chosen_scenario_id=req.chosen_scenario_id,
        chosen_scenario_name=req.chosen_scenario_name,
        candidate_set=req.candidate_set,
        alternatives_considered=alternatives,
        scenario_assumptions=req.scenario_assumptions,
        constraints=req.constraints,
        human_annotations=req.human_annotations,
        signed_by=req.signed_by,
    )
    saved = decision_record_store_v2.record_decision(record)
    return saved.to_dict()


@router.get("/decisions")
def list_decisions(club_id: str = Query("arsenal_fc")) -> list[dict[str, Any]]:
    """Lists immutable Decision Record V2 entries."""
    records = decision_record_store_v2.list_decisions(club_id=club_id)
    return [r.to_dict() for r in records]


@router.post("/follow-up")
def evaluate_follow_up(req: FollowUpRequest) -> dict[str, Any]:
    """Evaluates retrospective real-world realization vs simulated assumptions (§24)."""
    try:
        eval_result = decision_record_store_v2.evaluate_follow_up_alignment(
            decision_id=req.decision_id,
            realized_fee_eur=req.realized_fee_eur,
            realized_wage_eur=req.realized_wage_eur,
            realized_minutes=req.realized_minutes,
            observed_role=req.observed_role,
            observed_availability_pct=req.observed_availability_pct,
            observed_contribution=req.observed_contribution,
        )
        return eval_result.to_dict()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/copilot")
def query_copilot_v3(req: CopilotQueryRequest) -> dict[str, Any]:
    """Dispatches natural language query to deterministic Phase 13 scenario engines (§26)."""
    return copilot_v3_dispatcher.dispatch(query=req.query, club_id=req.club_id)
