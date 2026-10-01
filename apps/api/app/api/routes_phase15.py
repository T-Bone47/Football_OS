"""FastAPI Routes for Phase 15 Global Football Research and Adaptive Intelligence.

Exposes endpoints under /api/v1/research:
- GET /questions
- GET /hypotheses
- GET /cohorts
- GET /experiments & POST /experiments
- POST /validate
- GET /patterns & GET /patterns/{id}
- GET /cross-competition
- GET /league-translations
- GET /player-trajectories
- GET /role-transitions
- GET /tactical-patterns
- GET /transfer-market
- GET /model-errors
- GET /feature-candidates
- GET /validation-matrix
- GET /challengers
- GET /evidence/{research_id}
- POST /copilot
"""

from typing import Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.phase15.adaptive_candidates import get_adaptive_model_engine
from app.phase15.causality_guardrail import CausalityGuardrail
from app.phase15.cohort_engine import get_cohort_engine
from app.phase15.copilot_v5 import get_copilot_v5
from app.phase15.cross_competition_generalization import get_generalization_engine
from app.phase15.experiment_engine import get_experiment_engine
from app.phase15.feature_discovery import get_feature_discovery_engine
from app.phase15.global_validation_matrix import get_global_validation_matrix
from app.phase15.hypothesis_governance import get_hypothesis_engine
from app.phase15.league_translation import get_league_translation_engine
from app.phase15.model_error_research import get_model_error_engine
from app.phase15.pattern_discovery import get_pattern_discovery_engine
from app.phase15.player_trajectory_research import get_trajectory_research_engine
from app.phase15.research_evidence_graph import (
    ResearchEvidenceGraphBuilder,
    ResearchGraphEdge,
    ResearchGraphNode,
)
from app.phase15.research_models import (
    FeatureCandidate,
    PatternCandidate,
    ResearchCohort,
    ResearchExperiment,
    ResearchHypothesis,
    ResearchPromotionRecord,
    ResearchQuestion,
    ResearchValidation,
)
from app.phase15.research_questions import get_question_registry
from app.phase15.role_transition_research import get_role_transition_engine
from app.phase15.tactical_pattern_research import get_tactical_pattern_engine
from app.phase15.transfer_market_research import get_transfer_market_engine

router = APIRouter(prefix="/api/v1/research", tags=["Phase 15 - Global Research"])


# 1. Questions
@router.get("/questions", response_model=list[ResearchQuestion])
def list_research_questions() -> list[ResearchQuestion]:
    return get_question_registry().list_questions()


# 2. Hypotheses
@router.get("/hypotheses", response_model=list[ResearchHypothesis])
def list_hypotheses(state: str | None = None) -> list[ResearchHypothesis]:
    return get_hypothesis_engine().list_hypotheses()


# 3. Cohorts
@router.get("/cohorts", response_model=list[ResearchCohort])
def list_cohorts(cohort_type: str | None = None) -> list[ResearchCohort]:
    return get_cohort_engine().list_cohorts(cohort_type=cohort_type)


# 4. Experiments
@router.get("/experiments", response_model=list[ResearchExperiment])
def list_experiments() -> list[ResearchExperiment]:
    return get_experiment_engine().list_experiments()


class CreateExperimentRequest(BaseModel):
    experiment_id: str
    hypothesis_id: str
    cohort_id: str
    dataset_id: str
    features_used: list[str]
    methodology: str
    evaluation_window: dict[str, str]
    validation_strategy: str
    sample_size: int = 0
    competition_scope: list[str] = Field(default_factory=list)


@router.post("/experiments", response_model=ResearchExperiment)
def create_experiment(body: CreateExperimentRequest) -> ResearchExperiment:
    try:
        return get_experiment_engine().create_experiment(
            experiment_id=body.experiment_id,
            hypothesis_id=body.hypothesis_id,
            cohort_id=body.cohort_id,
            dataset_id=body.dataset_id,
            features_used=body.features_used,
            methodology=body.methodology,
            evaluation_window=body.evaluation_window,
            validation_strategy=body.validation_strategy,
            sample_size=body.sample_size,
            competition_scope=body.competition_scope,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class ValidateHypothesisRequest(BaseModel):
    hypothesis_id: str
    validation_id: str
    methodology: str
    holdout_sample_size: int
    holdout_window: dict[str, str]
    metrics: dict[str, float]
    leakage_detected: bool = False


@router.post("/validate", response_model=ResearchValidation)
def validate_hypothesis(body: ValidateHypothesisRequest) -> ResearchValidation:
    try:
        return get_hypothesis_engine().validate_hypothesis(
            hypothesis_id=body.hypothesis_id,
            validation_id=body.validation_id,
            methodology=body.methodology,
            holdout_sample_size=body.holdout_sample_size,
            holdout_window=body.holdout_window,
            metrics=body.metrics,
            leakage_detected=body.leakage_detected,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# 5. Patterns
@router.get("/patterns", response_model=list[PatternCandidate])
def list_patterns() -> list[PatternCandidate]:
    return get_pattern_discovery_engine().list_patterns()


@router.get("/patterns/{pattern_id}", response_model=PatternCandidate)
def get_pattern(pattern_id: str) -> PatternCandidate:
    try:
        return get_pattern_discovery_engine().get_pattern(pattern_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# 6. Cross-competition
@router.get("/cross-competition")
def list_cross_competition_evaluations(engine: str | None = None) -> list[dict[str, Any]]:
    evals = get_generalization_engine().list_evaluations(engine_name=engine)
    return [e.model_dump() for e in evals]


# 7. League Translations
@router.get("/league-translations")
def list_league_translations() -> list[dict[str, Any]]:
    reports = get_league_translation_engine().list_reports()
    return [r.model_dump() for r in reports]


# 8. Player Trajectories
@router.get("/player-trajectories")
def list_player_trajectories() -> list[dict[str, Any]]:
    reports = get_trajectory_research_engine().list_reports()
    return [r.model_dump() for r in reports]


# 9. Role Transitions
@router.get("/role-transitions")
def list_role_transitions() -> list[dict[str, Any]]:
    trans = get_role_transition_engine().list_transitions()
    return [t.model_dump() for t in trans]


# 10. Tactical Patterns
@router.get("/tactical-patterns")
def list_tactical_patterns() -> list[dict[str, Any]]:
    reports = get_tactical_pattern_engine().list_reports()
    return [r.model_dump() for r in reports]


# 11. Transfer Market Research
@router.get("/transfer-market")
def get_transfer_market_research() -> dict[str, Any]:
    engine = get_transfer_market_engine()
    slice_data = engine.compute_residual_slice("global_transfers")
    records = engine.list_records()
    return {
        "summary_residuals": slice_data.model_dump(),
        "recent_transfers": [r.model_dump() for r in records[:30]],
    }


# 12. Model Errors
@router.get("/model-errors")
def list_model_errors() -> list[dict[str, Any]]:
    reports = get_model_error_engine().list_reports()
    return [r.model_dump() for r in reports]


# 13. Feature Candidates
@router.get("/feature-candidates", response_model=list[FeatureCandidate])
def list_feature_candidates() -> list[FeatureCandidate]:
    return get_feature_discovery_engine().list_candidates()


# 14. Global Validation Matrix
@router.get("/validation-matrix")
def get_validation_matrix(engine: str | None = None, competition: str | None = None) -> dict[str, Any]:
    matrix = get_global_validation_matrix()
    cells = matrix.query_cells(engine=engine, competition=competition)
    summary = matrix.get_summary_coverage()
    return {
        "summary": summary,
        "cells": [c.model_dump() for c in cells],
    }


# 15. Challengers / Promotion Records
@router.get("/challengers", response_model=list[ResearchPromotionRecord])
def list_challenger_promotion_records() -> list[ResearchPromotionRecord]:
    return get_adaptive_model_engine().list_promotion_records()


# 16. Research Evidence Graph
@router.get("/evidence/{research_id}")
def get_research_evidence_graph(research_id: str) -> dict[str, Any]:
    nodes = [
        ResearchGraphNode(node_id="rq_001", node_type="QUESTION", label="League Adaptation", epistemic_status="ANALYSIS", provenance="research_registry"),
        ResearchGraphNode(node_id="hypo_001", node_type="HYPOTHESIS", label="Inverted FB Retention", epistemic_status="HYPOTHESIS", provenance="hypothesis_engine"),
        ResearchGraphNode(node_id="cohort_u23", node_type="COHORT", label="U23 Midfielders", epistemic_status="ANALYSIS", provenance="cohort_engine"),
        ResearchGraphNode(node_id="exp_001", node_type="EXPERIMENT", label="Propensity Study", epistemic_status="ANALYSIS", provenance="experiment_engine"),
        ResearchGraphNode(node_id="val_001", node_type="VALIDATION", label="Temporal Holdout", epistemic_status="ANALYSIS", provenance="validation_engine"),
    ]
    edges = [
        ResearchGraphEdge(source_id="rq_001", target_id="hypo_001", edge_type="FRAMES"),
        ResearchGraphEdge(source_id="hypo_001", target_id="cohort_u23", edge_type="USES_COHORT"),
        ResearchGraphEdge(source_id="cohort_u23", target_id="exp_001", edge_type="INPUT_TO"),
        ResearchGraphEdge(source_id="exp_001", target_id="val_001", edge_type="VALIDATED_BY"),
    ]
    graph = ResearchEvidenceGraphBuilder.build_graph(f"graph_{research_id}", nodes, edges)
    return graph.model_dump()


# 17. Copilot V5
class CopilotResearchRequest(BaseModel):
    query: str
    context: dict[str, Any] = Field(default_factory=dict)


@router.post("/copilot")
def query_copilot_research(body: CopilotResearchRequest) -> dict[str, Any]:
    dispatcher = get_copilot_v5()
    resp = dispatcher.dispatch(body.query, body.context)
    return resp.model_dump()
