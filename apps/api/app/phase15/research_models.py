"""Global Research Data Model for Phase 15.

Entities:
- ResearchQuestion
- ResearchHypothesis
- ResearchDataset
- ResearchCohort
- ResearchExperiment
- ResearchResult
- ResearchValidation
- FeatureCandidate
- ResearchPromotionRecord
- PatternCandidate
"""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

from app.phase15 import (
    DataSufficiencyStatus,
    EpistemicModality,
    GeneralizationDomain,
    HypothesisValidationResult,
    PatternFamily,
    ResearchLifecycleState,
)


class ResearchEntityBase(BaseModel):
    research_id: str
    version: str = "1.0.0"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dataset_version: str = "dataset_v15.0"
    feature_set_version: str = "features_v15.0"
    calculation_version: str = "calc_v15.0"
    model_version: str | None = None
    provenance: str = "research_workspace_v15"
    epistemic_status: EpistemicModality = EpistemicModality.ANALYSIS
    sample_size: int = Field(ge=0, default=0)
    competition_scope: list[str] = Field(default_factory=list)
    temporal_scope: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchQuestion(ResearchEntityBase):
    question_id: str
    title: str
    description: str
    author: str = "scout_research_team"
    tags: list[str] = Field(default_factory=list)
    status: str = "OPEN"  # OPEN, INVESTIGATING, CONCLUDED


class ResearchHypothesis(ResearchEntityBase):
    hypothesis_id: str
    question_id: str | None = None
    statement: str
    epistemic_status: EpistemicModality = EpistemicModality.HYPOTHESIS
    lifecycle_state: ResearchLifecycleState = ResearchLifecycleState.HYPOTHESIS
    source_patterns: list[str] = Field(default_factory=list)
    supporting_observations: list[dict[str, Any]] = Field(default_factory=list)
    contradicting_observations: list[dict[str, Any]] = Field(default_factory=list)
    affected_competitions: list[str] = Field(default_factory=list)
    affected_seasons: list[str] = Field(default_factory=list)
    confounders: list[str] = Field(default_factory=list)
    uncertainty_description: str = "High initial uncertainty prior to independent holdout testing"
    is_causal_claim: bool = False  # Must be False by policy


class ResearchCohort(ResearchEntityBase):
    cohort_id: str
    cohort_type: str  # PLAYER, TRANSFER, TEAM, MATCH
    name: str
    filter_criteria: dict[str, Any]
    entity_ids: list[str] = Field(default_factory=list)
    is_immutable: bool = False
    cohort_hash: str = ""
    parent_version: str | None = None


class ResearchDataset(ResearchEntityBase):
    dataset_id: str
    name: str
    temporal_cutoff: str  # Max timestamp for data inclusion (T)
    row_count: int
    data_hash: str
    sources: list[str] = Field(default_factory=list)


class ResearchValidation(BaseModel):
    validation_id: str
    methodology: str  # INDEPENDENT_COHORT, TEMPORAL_HOLDOUT, COMPETITION_HOLDOUT, NEGATIVE_CONTROL
    sample_size: int
    holdout_window: dict[str, str]
    result: HypothesisValidationResult
    metrics: dict[str, float]
    leakage_audit_passed: bool
    limitations: list[str] = Field(default_factory=list)
    non_causal_statement: str


class ResearchResult(BaseModel):
    result_id: str
    effect_estimate: float
    confidence_interval: tuple[float, float]
    p_value_or_posterior: float | None = None
    subgroup_breakdown: dict[str, dict[str, Any]] = Field(default_factory=dict)
    summary_findings: list[str] = Field(default_factory=list)
    non_causal_statement: str


class ResearchExperiment(ResearchEntityBase):
    experiment_id: str
    hypothesis_id: str
    cohort_id: str
    dataset_id: str
    features_used: list[str] = Field(default_factory=list)
    methodology: str
    evaluation_window: dict[str, str]
    validation_strategy: str
    experiment_hash: str = ""
    is_completed: bool = False
    result: ResearchResult | None = None
    validation: ResearchValidation | None = None
    limitations: list[str] = Field(default_factory=list)


class FeatureCandidate(ResearchEntityBase):
    candidate_id: str
    feature_name: str
    target_metric: str
    rationale: str
    discovered_in_experiments: list[str] = Field(default_factory=list)
    effect_magnitude: float
    stability_score: float
    leakage_audited: bool = True
    ood_sensitivity: str = "LOW"
    competition_coverage: list[str] = Field(default_factory=list)
    production_ready: bool = False  # NEVER auto-promoted to prod


class ResearchPromotionRecord(BaseModel):
    promotion_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    target_type: str  # MODEL, FEATURE, TACTICAL_RULE
    candidate_id: str
    champion_id: str | None = None
    evaluation_windows: list[dict[str, Any]]
    subgroup_parity_passed: bool
    governed_approval_author: str
    promotion_status: str  # SHADOW, CANARY, REJECTED, PROMOTED
    justification: str


class PatternCandidate(BaseModel):
    pattern_id: str
    family: PatternFamily
    title: str
    description: str
    sample_size: int
    temporal_scope: dict[str, str]
    competition_scope: list[str]
    effect_estimate: float
    uncertainty: str
    subgroup_breakdown: dict[str, Any] = Field(default_factory=dict)
    confounder_warnings: list[str] = Field(default_factory=list)
    data_quality_status: DataSufficiencyStatus = DataSufficiencyStatus.DATA_AVAILABLE
    generalization_domain: GeneralizationDomain = GeneralizationDomain.IN_DOMAIN
    epistemic_status: EpistemicModality = EpistemicModality.ANALYSIS
    non_causal_statement: str
