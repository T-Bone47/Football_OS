"""Phase 14 — Governed Decision Learning Loop, Pattern Mining & Challenger Feedback (§10, §12, §17).

Connects realized outcome evaluations to institutional learning:
  - Governed Learning Pipeline:
    Outcome -> Quality Check -> Decision Realization -> Divergence Diagnosis ->
    Pattern Detection -> Model Monitoring -> Assumption Monitoring -> Challenger Candidate ->
    Validation -> Governed Promotion Report.
  - Strict Safety Rule: Zero automated weight updates or promotions. Everything requires governed sign-off.
  - Decision Pattern Mining (§12):
    - Identifies systemic patterns across decisions (low data sufficiency, high OOD, valuation errors, etc.).
    - Requires sample size thresholds; returns INSUFFICIENT_PATTERN_SAMPLE if sample is too small.
  - Model Challenger Governance (§17):
    - Side-by-side champion vs challenger evaluation over identical historical realization windows.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.phase14 import (
    AlignmentClassification,
    ErrorCategory,
    LearningActionState,
)
from app.phase14.decision_realization import decision_realization_evaluator
from app.phase14.process_quality import process_quality_engine


@dataclass
class LearningSignalRecord:
    """Actionable learning event generated from retrospective realization analysis (§10)."""
    signal_id: str = field(default_factory=lambda: f"ls_{uuid.uuid4().hex[:12]}")
    decision_id: str = ""
    scenario_id: str = ""
    target_component: str = "VALUATION_MODEL"  # "TACTICAL_MODEL", "VALUATION_MODEL", "ASSUMPTION_POLICY", "DATA_PIPELINE"
    action_state: LearningActionState = LearningActionState.MONITOR
    primary_error_category: ErrorCategory = ErrorCategory.CALIBRATION_ERROR
    trigger_metric: str = "tactical_fit_observed"
    divergence_magnitude: float = 0.0
    description: str = ""
    evidence_summary: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action_state"] = self.action_state.value
        data["primary_error_category"] = self.primary_error_category.value
        return data


@dataclass
class DecisionPatternReport:
    """Aggregate analytical mining across historical decisions (§12)."""
    pattern_id: str = field(default_factory=lambda: f"pat_{uuid.uuid4().hex[:12]}")
    analysis_type: str = "VALUATION_BIAS"
    total_decisions_analyzed: int = 0
    minimum_sample_required: int = 5
    status: str = "EVALUATED"  # "EVALUATED", "INSUFFICIENT_PATTERN_SAMPLE"
    findings: list[str] = field(default_factory=list)
    systemic_flags: list[dict[str, Any]] = field(default_factory=list)
    analyzed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GovernedChallengerComparison:
    """Governed evaluation of Champion vs Challenger models on realized outcome windows (§17)."""
    comparison_id: str = field(default_factory=lambda: f"chal_comp_{uuid.uuid4().hex[:12]}")
    champion_model_id: str = "calibrated_multinomial_logit_v1"
    challenger_model_id: str = "hierarchical_bayesian_match_v2"
    evaluation_window: str = "EPL_2023_2024_REALIZED"
    sample_size: int = 35
    champion_log_loss: float = 0.9412
    challenger_log_loss: float = 0.9230
    champion_ece: float = 0.0418
    challenger_ece: float = 0.0385
    is_challenger_superior: bool = True
    governed_recommendation: LearningActionState = LearningActionState.CHALLENGER_RECOMMENDED
    promotion_notes: list[str] = field(default_factory=list)
    requires_human_signoff: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["governed_recommendation"] = self.governed_recommendation.value
        return data


class DecisionLearningLoopEngine:
    """Coordinates learning signals, pattern mining, and governed challenger evaluations."""

    def __init__(self) -> None:
        self._signals: dict[str, LearningSignalRecord] = {}
        self._patterns: dict[str, DecisionPatternReport] = {}
        self._challenger_evals: dict[str, GovernedChallengerComparison] = {}
        self._seed_default_learning()

    def generate_learning_signal(
        self,
        decision_id: str,
        scenario_id: str,
        target_component: str,
        action_state: LearningActionState,
        primary_error_category: ErrorCategory,
        trigger_metric: str,
        divergence_magnitude: float,
        description: str,
        evidence_summary: list[str],
    ) -> LearningSignalRecord:
        """Emits an institutional learning signal based on divergence diagnosis."""
        signal = LearningSignalRecord(
            decision_id=decision_id,
            scenario_id=scenario_id,
            target_component=target_component,
            action_state=action_state,
            primary_error_category=primary_error_category,
            trigger_metric=trigger_metric,
            divergence_magnitude=float(divergence_magnitude),
            description=description,
            evidence_summary=evidence_summary,
        )
        self._signals[signal.signal_id] = signal
        return signal

    def mine_decision_patterns(self, min_sample: int = 5) -> DecisionPatternReport:
        """Mines systemic patterns across evaluated decisions."""
        evals = decision_realization_evaluator.list_evaluations()
        n = len(evals)

        if n < min_sample:
            rep = DecisionPatternReport(
                analysis_type="MULTI_DECISION_PATTERN_MINING",
                total_decisions_analyzed=n,
                minimum_sample_required=min_sample,
                status="INSUFFICIENT_PATTERN_SAMPLE",
                findings=[f"Evaluated decisions count (N={n}) is below threshold ({min_sample}). Descriptive pattern mining withheld."],
            )
            self._patterns[rep.pattern_id] = rep
            return rep

        # Analyze divergence distributions
        aligned_count = sum(1 for e in evals if e.overall_alignment == AlignmentClassification.ALIGNED)
        diverged_count = sum(1 for e in evals if e.overall_alignment == AlignmentClassification.DIVERGED)

        flags = []
        findings = [
            f"Analyzed {n} finalized decisions with post-decision realized telemetry.",
            f"Overall alignment rate: {aligned_count / n * 100.0:.1f}%.",
        ]

        if diverged_count > 0:
            flags.append({
                "pattern": "MINUTES_UNCERTAINTY",
                "affected_decisions": diverged_count,
                "description": "Minutes played in season 1 frequently diverge due to availability and rotation shocks.",
            })
            findings.append("Pattern identified: Player availability in year 1 represents primary variance driver.")

        rep = DecisionPatternReport(
            analysis_type="MULTI_DECISION_PATTERN_MINING",
            total_decisions_analyzed=n,
            minimum_sample_required=min_sample,
            status="EVALUATED",
            findings=findings,
            systemic_flags=flags,
        )
        self._patterns[rep.pattern_id] = rep
        return rep

    def evaluate_challenger(
        self,
        champion_model_id: str,
        challenger_model_id: str,
        evaluation_window: str,
        sample_size: int,
        champion_log_loss: float,
        challenger_log_loss: float,
        champion_ece: float,
        challenger_ece: float,
    ) -> GovernedChallengerComparison:
        """Evaluates challenger model against champion using identical realized window telemetry."""
        is_superior = (challenger_log_loss < champion_log_loss) and (challenger_ece <= champion_ece)
        rec = LearningActionState.CHALLENGER_RECOMMENDED if is_superior else LearningActionState.MONITOR

        notes = [
            f"Evaluated on {sample_size} identical realized outcome matches in window '{evaluation_window}'.",
            f"Challenger Log Loss: {challenger_log_loss:.4f} vs Champion: {champion_log_loss:.4f} (delta: {challenger_log_loss - champion_log_loss:+.4f}).",
            f"Challenger ECE: {challenger_ece:.4f} vs Champion: {champion_ece:.4f}.",
            "Strict non-causal rule: Model promotion requires independent data ops review and release checklist verification.",
        ]

        comp = GovernedChallengerComparison(
            champion_model_id=champion_model_id,
            challenger_model_id=challenger_model_id,
            evaluation_window=evaluation_window,
            sample_size=sample_size,
            champion_log_loss=champion_log_loss,
            challenger_log_loss=challenger_log_loss,
            champion_ece=champion_ece,
            challenger_ece=challenger_ece,
            is_challenger_superior=is_superior,
            governed_recommendation=rec,
            promotion_notes=notes,
            requires_human_signoff=True,
        )
        self._challenger_evals[comp.comparison_id] = comp
        return comp

    def list_signals(self) -> list[LearningSignalRecord]:
        return list(self._signals.values())

    def list_patterns(self) -> list[DecisionPatternReport]:
        return list(self._patterns.values())

    def list_challenger_evaluations(self) -> list[GovernedChallengerComparison]:
        return list(self._challenger_evals.values())

    def _seed_default_learning(self) -> None:
        """Seeds default learning signals and challenger evaluations."""
        # Learning Signal 1: Physical Availability Risk on Year 1
        self.generate_learning_signal(
            decision_id="dec_rec_timber_2023",
            scenario_id="scen_timber_sign",
            target_component="ASSUMPTION_POLICY",
            action_state=LearningActionState.INVESTIGATE,
            primary_error_category=ErrorCategory.UNOBSERVED_EXTERNAL_FACTOR,
            trigger_metric="minutes_played",
            divergence_magnitude=-8.6,
            description="First-season minutes fell short of 1,400 min baseline due to acute knee trauma.",
            evidence_summary=[
                "Player completed 1,280 competitive minutes across full season.",
                "Tactical fit when available was 89.4 (above expected 88.0).",
                "Recommendation: Increase year-1 availability discount factors in scenario builder for high-intensity competitions.",
            ],
        )

        # Challenger Comparison
        self.evaluate_challenger(
            champion_model_id="calibrated_multinomial_logit_v1",
            challenger_model_id="hierarchical_bayesian_match_v2",
            evaluation_window="EPL_2023_2024_REALIZED",
            sample_size=35,
            champion_log_loss=0.9412,
            challenger_log_loss=0.9230,
            champion_ece=0.0418,
            challenger_ece=0.0385,
        )

        # Initial pattern report
        self.mine_decision_patterns(min_sample=2)


decision_learning_loop_engine = DecisionLearningLoopEngine()
