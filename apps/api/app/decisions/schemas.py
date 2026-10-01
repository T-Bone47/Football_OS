"""Schemas for Unified Decision Intelligence & Recruitment Engine (Phase 7).

Enforces decomposable multi-dimensional candidate evaluation, explicit hard constraint tracking,
unconflated confidence decomposition (Data, Model, Decision), and evidence graph traceability.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


DECISION_CALCULATION_VERSION = "decision_intelligence_v1"
DECISION_FEATURE_SET_VERSION = "recruitment_v1"


class ConfidenceDecomposition(BaseModel):
    """Separates Model, Data, and Decision confidence without false precision."""
    model_config = ConfigDict(extra="ignore")

    data_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in historical sample depth and completeness")
    model_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the statistical models' predictive calibration")
    decision_confidence: float = Field(..., ge=0.0, le=1.0, description="Combined decision integrity based on evidence convergence")
    confidence_tier: str = "MODERATE"  # HIGH, MODERATE, LOW, VERY_LOW
    data_status: str = "DECISION_AVAILABLE"  # DECISION_AVAILABLE, LOW_CONFIDENCE, INSUFFICIENT_DATA, OUT_OF_DISTRIBUTION, PARTIAL_EVIDENCE
    sufficiency_factors: list[str] = Field(default_factory=list)
    uncertainty_drivers: list[str] = Field(default_factory=list)


class HardConstraintResult(BaseModel):
    """Explicit verification of non-negotiable boundaries; never overridden by soft scores."""
    model_config = ConfigDict(extra="ignore")

    passed: bool
    # None = the constraint could not be verified (the value is unknown).
    checks: dict[str, bool | None] = Field(default_factory=dict)
    exclusion_reasons: list[str] = Field(default_factory=list)


class DimensionPerformance(BaseModel):
    """Observed performance and contribution intelligence."""
    model_config = ConfigDict(extra="ignore")

    contribution_rating: float = Field(..., ge=0.0, le=100.0)
    percentile_in_role: float | None = Field(None, ge=0.0, le=100.0)
    offensive_impact: float | None = None
    defensive_impact: float | None = None
    trajectory: str = "STABLE"  # ASCENDING, STABLE, PEAK, DESCENDING
    sample_minutes: int = 0
    sample_matches: int = 0


class DimensionTactical(BaseModel):
    """Tactical fit, role compatibility, and system suitability."""
    model_config = ConfigDict(extra="ignore")

    tactical_fit_score: float = Field(..., ge=0.0, le=100.0)
    role_compatibility: float = Field(..., ge=0.0, le=100.0)
    system_name: str
    target_role: str
    strengths: list[str] = Field(default_factory=list)
    vulnerabilities: list[str] = Field(default_factory=list)


class DimensionSimilarity(BaseModel):
    """Multi-dimensional similarity to benchmark or player being replaced."""
    model_config = ConfigDict(extra="ignore")

    overall_similarity: float = Field(..., ge=0.0, le=1.0)
    statistical_similarity: float = Field(..., ge=0.0, le=1.0)
    role_similarity: float = Field(..., ge=0.0, le=1.0)
    replacement_similarity: float | None = None
    comparison_target_name: str | None = None


class DimensionMarket(BaseModel):
    """Market valuation, comparables, and budget feasibility."""
    model_config = ConfigDict(extra="ignore")

    estimated_value_eur: float = Field(..., ge=0.0)
    fee_range_low_eur: float = Field(..., ge=0.0)
    fee_range_high_eur: float = Field(..., ge=0.0)
    budget_eur: float | None = None
    affordability_status: str = "AFFORDABLE"  # AFFORDABLE, BUDGET_STRETCH, BEYOND_BUDGET
    value_opportunity_index: float = 1.0  # >1.0 indicates market discount/opportunity
    comparable_transfers_count: int = 0


class DimensionRisk(BaseModel):
    """Transfer risk classification and multi-dimensional vulnerability."""
    model_config = ConfigDict(extra="ignore")

    overall_risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    performance_risk: float | None = Field(None, ge=0.0, le=1.0)
    adaptation_risk: float | None = Field(None, ge=0.0, le=1.0)
    financial_risk: float | None = Field(None, ge=0.0, le=1.0)
    availability_risk: float | None = Field(None, ge=0.0, le=1.0)
    key_risk_drivers: list[str] = Field(default_factory=list)


class DimensionSquadImpact(BaseModel):
    """Projected squad depth, role coverage, and roster balance."""
    model_config = ConfigDict(extra="ignore")

    depth_status_before: str = "UNKNOWN"
    depth_status_after: str = "UNKNOWN"
    formation_slot: str
    role_coverage_change: float = 0.0  # Positive indicates improvement
    age_profile_impact: str = "NEUTRAL"
    net_squad_upgrade: bool = True


class DimensionPredictionImpact(BaseModel):
    """Counterfactual match prediction impact if integrated into target fixture."""
    model_config = ConfigDict(extra="ignore")

    match_id: uuid.UUID | None = None
    baseline_win_prob: float | None = None
    scenario_win_prob: float | None = None
    win_prob_delta: float | None = None
    baseline_xg: float | None = None
    scenario_xg: float | None = None
    counterfactual_note: str = (
        "Model scenario projection under hypothetical lineup integration; "
        "not an observed empirical match result."
    )


class MultiDimensionalCandidateAssessment(BaseModel):
    """Completely decomposable, explainable assessment for a single recruitment candidate."""
    model_config = ConfigDict(extra="ignore")

    candidate_id: uuid.UUID
    player_name: str
    current_club_id: uuid.UUID | None = None
    current_club_name: str | None = None
    age: float | None = None
    primary_position: str | None = None
    target_role: str
    minutes_played: int | None = None  # None = not reported by any provider
    competition_name: str | None = None

    hard_constraints: HardConstraintResult
    # Phase 18 (R23): a dimension is present only when stored evidence backs
    # it. Otherwise it is None and dimension_status says why.
    performance: DimensionPerformance | None = None
    tactical: DimensionTactical | None = None
    similarity: DimensionSimilarity | None = None
    market: DimensionMarket | None = None
    risk: DimensionRisk | None = None
    squad_impact: DimensionSquadImpact | None = None
    # dimension -> OBSERVED | MODELLED | INSUFFICIENT_DATA | UNKNOWN | MODEL_UNVERIFIED | NOT_ASSESSED
    dimension_status: dict[str, str] = Field(default_factory=dict)
    # RANKED (enough evidence to compare) or INSUFFICIENT_EVIDENCE (listed, never recommended)
    ranking_status: str = "INSUFFICIENT_EVIDENCE"
    ranking_score: float | None = None
    prediction_impact: DimensionPredictionImpact | None = None
    confidence: ConfidenceDecomposition

    why_matches: list[str] = Field(default_factory=list)
    where_differs: list[str] = Field(default_factory=list)
    evidence_node_ids: list[str] = Field(default_factory=list)


class EvidenceGraphNode(BaseModel):
    """Traceable evidence node representing an atomic piece of intelligence."""
    model_config = ConfigDict(extra="ignore")

    id: str
    node_type: str  # PLAYER, CONTRIBUTION, ROLE, TACTICAL_FIT, SIMILARITY, VALUATION, RISK, SQUAD, PREDICTION, DECISION
    label: str
    value: Any = None
    confidence: float = 1.0
    provenance: str = "FOOTBALL_INTELLIGENCE_OS"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvidenceGraphEdge(BaseModel):
    """Directed connection between evidence elements."""
    model_config = ConfigDict(extra="ignore")

    from_node: str
    to_node: str
    relationship: str  # FEEDS_INTO, CONSTRAINS, SUPPORTS, QUALIFIES, COUNTERFACTUAL
    weight: float = 1.0


class EvidenceGraphResponse(BaseModel):
    """Traceable Directed Acyclic Graph (DAG) for a decision assessment."""
    model_config = ConfigDict(extra="ignore")

    decision_id: uuid.UUID
    nodes: list[EvidenceGraphNode] = Field(default_factory=list)
    edges: list[EvidenceGraphEdge] = Field(default_factory=list)
    evidence_hash: str = ""


class DecisionAssessment(BaseModel):
    """Top-level canonical decision assessment object."""
    model_config = ConfigDict(extra="ignore")

    decision_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    decision_type: str  # RECRUITMENT, REPLACEMENT, TRANSFER_SCENARIO, SQUAD_NEED
    subject_type: str  # SQUAD, PLAYER, MATCH, POSITION
    subject_id: uuid.UUID | None = None
    scenario_id: uuid.UUID | None = None
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    calculation_version: str = DECISION_CALCULATION_VERSION
    feature_version: str = DECISION_FEATURE_SET_VERSION

    summary: str
    total_candidates_analyzed: int = 0
    passed_candidates_count: int = 0
    excluded_candidates_count: int = 0
    candidates: list[MultiDimensionalCandidateAssessment] = Field(default_factory=list)

    confidence: ConfidenceDecomposition
    evidence_graph: EvidenceGraphResponse | None = None
    evidence_hash: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# REQUEST & RESPONSE CONTRACTS
# ============================================================
class RecruitmentTargetRequest(BaseModel):
    """Input parameters for deterministic recruitment target identification."""
    model_config = ConfigDict(extra="ignore")

    club_id: uuid.UUID | None = None
    target_position: str
    target_role: str | None = None
    tactical_context_id: str = "possession_dominant_433"
    formation: str = "4-3-3"
    budget_eur: float | None = None
    # Phase 18 (R23): a constraint applies only when the caller sets it.
    min_age: float | None = None
    max_age: float | None = None
    min_minutes: int | None = None
    risk_tolerance: str = "MEDIUM"  # LOW, MEDIUM, HIGH, ALL
    limit: int = 15
    as_of: datetime | None = None


class RecruitmentTargetResponse(BaseModel):
    """Comprehensive recruitment target decision intelligence output."""
    model_config = ConfigDict(extra="ignore")

    decision: DecisionAssessment
    # RANKED | INSUFFICIENT_EVIDENCE | NO_ELIGIBLE_CANDIDATES
    status: str = "NO_ELIGIBLE_CANDIDATES"
    top_recommendations: list[MultiDimensionalCandidateAssessment]
    # Passed the hard constraints but lack the evidence to be ranked; never recommended.
    insufficient_evidence: list[MultiDimensionalCandidateAssessment] = Field(default_factory=list)
    excluded_summaries: list[dict[str, Any]] = Field(default_factory=list)


class ReplacementDecisionRequest(BaseModel):
    """Input parameters for replacing a specific player."""
    model_config = ConfigDict(extra="ignore")

    player_id_to_replace: uuid.UUID
    club_id: uuid.UUID | None = None
    budget_eur: float | None = None
    target_role: str | None = None
    tactical_context_id: str = "possession_dominant_433"
    formation: str = "4-3-3"
    min_similarity: float = 0.50
    limit: int = 10
    as_of: datetime | None = None


class ReplacementDecisionResponse(BaseModel):
    """Replacement player intelligence with 'Why Matches' & 'Where Differs' evidence."""
    model_config = ConfigDict(extra="ignore")

    replaced_player_id: uuid.UUID
    replaced_player_name: str
    replaced_player_role: str
    status: str = "NO_ELIGIBLE_CANDIDATES"
    decision: DecisionAssessment
    top_replacements: list[MultiDimensionalCandidateAssessment]
    insufficient_evidence: list[MultiDimensionalCandidateAssessment] = Field(default_factory=list)
    excluded_summaries: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioRosterChange(BaseModel):
    """Individual player transfer specification within a scenario."""
    model_config = ConfigDict(extra="ignore")

    player_id: uuid.UUID
    direction: Literal["IN", "OUT"]
    fee_eur: float | None = None
    wage_eur: float | None = None


class TransferScenarioDecisionRequest(BaseModel):
    """Multi-player transfer scenario modeling request."""
    model_config = ConfigDict(extra="ignore")

    club_id: uuid.UUID
    roster_changes: list[ScenarioRosterChange]
    formation: str = "4-3-3"
    budget_eur: float | None = None
    target_match_id: uuid.UUID | None = None
    as_of: datetime | None = None


class TransferScenarioDecisionResponse(BaseModel):
    """Impact of multi-player transfers on squad depth, finances, risk, and match forecast."""
    model_config = ConfigDict(extra="ignore")

    decision: DecisionAssessment
    financial_impact: dict[str, Any]
    squad_impact_summary: dict[str, Any]
    risk_profile_before: str
    risk_profile_after: str
    match_prediction_impact: DimensionPredictionImpact | None = None


class CandidateComparisonRequest(BaseModel):
    """Side-by-side comparison of specific candidate players."""
    model_config = ConfigDict(extra="ignore")

    candidate_ids: list[uuid.UUID] = Field(..., min_length=2, max_length=5)
    target_role: str | None = None
    tactical_context_id: str = "possession_dominant_433"
    club_id: uuid.UUID | None = None
    as_of: datetime | None = None


class CandidateComparisonResponse(BaseModel):
    """Multi-player comparison matrix across all 6 analytical dimensions."""
    model_config = ConfigDict(extra="ignore")

    candidates: list[MultiDimensionalCandidateAssessment]
    # Requested ids with no player record: reported, never replaced by others.
    not_found_candidate_ids: list[uuid.UUID] = Field(default_factory=list)
    trade_off_analysis: list[dict[str, Any]] = Field(default_factory=list)
    # A leader is named only among candidates that have that dimension.
    dimension_leaders: dict[str, str] = Field(default_factory=dict)
