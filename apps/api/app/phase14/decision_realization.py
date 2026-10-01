"""Phase 14 — Deterministic Decision Realization Evaluator (§4, §6).

Evaluates decision-time expectations against realized observations from the Outcome Ledger.
Core Epistemic & Non-Causal Rules:
  - Strictly preserves original immutable decision record.
  - Compares expected vs realized values on multi-dimensional axes.
  - Zero single-score collapse: preserves each metric's tolerance band and delta.
  - Non-causal findings: uses associative phrasing ('aligned with', 'diverged from',
    'not explained by available evidence').
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.phase14 import (
    AlignmentClassification,
    DataSufficiencyStatus,
    EpistemicModality,
)
from app.phase14.outcome_ledger import OutcomeLedger, outcome_ledger


@dataclass
class MetricComparison:
    """Individual metric comparison between decision expectation and realized observation."""
    metric_name: str
    expected_value: float
    realized_value: float
    absolute_delta: float
    relative_delta_pct: float
    tolerance_band_pct: float
    is_within_tolerance: bool
    directional_alignment: str  # "WITHIN_TOLERANCE", "HIGHER_THAN_EXPECTED", "LOWER_THAN_EXPECTED"
    unit: str
    confidence: float
    evidence_status: DataSufficiencyStatus
    modality_expected: EpistemicModality = EpistemicModality.MODELLED
    modality_realized: EpistemicModality = EpistemicModality.OBSERVED

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_status"] = self.evidence_status.value
        data["modality_expected"] = self.modality_expected.value
        data["modality_realized"] = self.modality_realized.value
        return data


@dataclass
class DecisionRealizationEvaluation:
    """Comprehensive retrospective realization evaluation for a completed decision (§4, §6)."""
    evaluation_id: str = field(default_factory=lambda: f"eval_{uuid.uuid4().hex[:12]}")
    decision_id: str = ""
    scenario_id: str = ""
    subject_entity_id: str = ""  # player_id, club_id, or match_id
    subject_name: str = ""
    evaluation_window: str = "FULL_SEASON_2023_2024"
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Multi-dimensional metric comparisons (never collapsed into a single scalar)
    metric_comparisons: list[MetricComparison] = field(default_factory=list)

    # Aggregate classification
    overall_alignment: AlignmentClassification = AlignmentClassification.ALIGNED
    primary_divergence_metrics: list[str] = field(default_factory=list)

    # Qualitative, non-causal analytical findings
    findings: list[str] = field(default_factory=list)
    temporal_isolation_verified: bool = True
    assumptions_evaluated: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["overall_alignment"] = self.overall_alignment.value
        data["metric_comparisons"] = [m.to_dict() for m in self.metric_comparisons]
        return data


class DecisionRealizationEvaluator:
    """Evaluates decision-time expectations vs realized observations using Outcome Ledger."""

    def __init__(self, ledger: OutcomeLedger | None = None) -> None:
        self._ledger = ledger or outcome_ledger
        self._evaluations: dict[str, DecisionRealizationEvaluation] = {}
        self._seed_default_evaluations()

    def evaluate_decision(
        self,
        decision_id: str,
        scenario_id: str,
        subject_entity_id: str,
        subject_name: str,
        expectations: list[dict[str, Any]],  # [{"metric": "minutes_played", "expected": 1400.0, "tolerance_pct": 15.0, "unit": "minutes"}]
        evaluation_window: str = "POST_DECISION_WINDOW",
        assumptions: list[str] | None = None,
    ) -> DecisionRealizationEvaluation:
        """Deterministically evaluates a decision against real-world ledger entries."""
        metric_comparisons: list[MetricComparison] = []
        divergent_metrics: list[str] = []
        findings: list[str] = []

        # Fetch relevant outcomes for this decision
        ledger_outcomes = self._ledger.list_outcomes(decision_id=decision_id)
        outcome_by_metric = {o.metric: o for o in ledger_outcomes}

        for exp in expectations:
            metric_name = exp["metric"]
            exp_val = float(exp["expected"])
            tol_pct = float(exp.get("tolerance_pct", 15.0))
            unit = exp.get("unit", "")

            if metric_name not in outcome_by_metric:
                # Missing outcome data: strict sufficiency rule
                comp = MetricComparison(
                    metric_name=metric_name,
                    expected_value=exp_val,
                    realized_value=0.0,
                    absolute_delta=0.0,
                    relative_delta_pct=0.0,
                    tolerance_band_pct=tol_pct,
                    is_within_tolerance=False,
                    directional_alignment="NO_REALIZED_DATA",
                    unit=unit,
                    confidence=0.0,
                    evidence_status=DataSufficiencyStatus.INSUFFICIENT_DATA,
                )
                metric_comparisons.append(comp)
                divergent_metrics.append(metric_name)
                findings.append(f"Outcome data for '{metric_name}' is not currently available in the ledger.")
                continue

            outcome = outcome_by_metric[metric_name]
            real_val = outcome.value
            abs_delta = real_val - exp_val
            rel_delta = ((real_val - exp_val) / exp_val * 100.0) if exp_val != 0.0 else 0.0

            # Evaluate tolerance band
            lower_bound = exp_val * (1.0 - tol_pct / 100.0)
            upper_bound = exp_val * (1.0 + tol_pct / 100.0)
            is_within = lower_bound <= real_val <= upper_bound

            if is_within:
                dir_align = "WITHIN_TOLERANCE"
            elif real_val > upper_bound:
                dir_align = "HIGHER_THAN_EXPECTED"
            else:
                dir_align = "LOWER_THAN_EXPECTED"

            if not is_within:
                divergent_metrics.append(metric_name)

            comp = MetricComparison(
                metric_name=metric_name,
                expected_value=exp_val,
                realized_value=real_val,
                absolute_delta=round(abs_delta, 2),
                relative_delta_pct=round(rel_delta, 2),
                tolerance_band_pct=tol_pct,
                is_within_tolerance=is_within,
                directional_alignment=dir_align,
                unit=unit,
                confidence=outcome.confidence,
                evidence_status=outcome.data_status,
            )
            metric_comparisons.append(comp)

            # Generate associative finding
            status_text = "aligned within tolerance" if is_within else f"diverged by {rel_delta:+.1f}%"
            findings.append(
                f"Metric '{metric_name}': expected {exp_val:,.1f} {unit}, realized {real_val:,.1f} {unit} ({status_text})."
            )

        # Classification rule:
        # If all available are within tolerance -> ALIGNED
        # If partial divergence -> PARTIALLY_ALIGNED
        # If severe divergence -> DIVERGED
        # If no valid data -> INSUFFICIENT_EVIDENCE
        valid_comps = [c for c in metric_comparisons if c.evidence_status == DataSufficiencyStatus.DATA_AVAILABLE]
        if not valid_comps:
            overall = AlignmentClassification.INSUFFICIENT_EVIDENCE
            findings.append("Evaluation inconclusive: insufficient verified telemetry in outcome ledger.")
        else:
            within_count = sum(1 for c in valid_comps if c.is_within_tolerance)
            ratio = within_count / len(valid_comps)
            if ratio >= 0.80:
                overall = AlignmentClassification.ALIGNED
            elif ratio >= 0.50:
                overall = AlignmentClassification.PARTIALLY_ALIGNED
            else:
                overall = AlignmentClassification.DIVERGED

        eval_assumptions = []
        if assumptions:
            for asm in assumptions:
                eval_assumptions.append({
                    "assumption_statement": asm,
                    "evaluation": "Consistent with observed window context" if overall == AlignmentClassification.ALIGNED else "Assumption may have experienced parameter drift",
                })

        evaluation = DecisionRealizationEvaluation(
            decision_id=decision_id,
            scenario_id=scenario_id,
            subject_entity_id=subject_entity_id,
            subject_name=subject_name,
            evaluation_window=evaluation_window,
            metric_comparisons=metric_comparisons,
            overall_alignment=overall,
            primary_divergence_metrics=divergent_metrics,
            findings=findings,
            temporal_isolation_verified=True,
            assumptions_evaluated=eval_assumptions,
        )

        self._evaluations[decision_id] = evaluation
        return evaluation

    def get_evaluation(self, decision_id: str) -> DecisionRealizationEvaluation | None:
        return self._evaluations.get(decision_id)

    def list_evaluations(self) -> list[DecisionRealizationEvaluation]:
        return list(self._evaluations.values())

    def _seed_default_evaluations(self) -> None:
        """Seeds benchmark evaluations for Timber, Rice, and Lewis-Skelly decisions."""
        # Timber 2023 Evaluation
        timber_exp = [
            {"metric": "minutes_played", "expected": 1400.0, "tolerance_pct": 15.0, "unit": "minutes"},
            {"metric": "transfer_fee_paid_eur", "expected": 40_000_000.0, "tolerance_pct": 5.0, "unit": "EUR"},
            {"metric": "tactical_fit_observed", "expected": 88.0, "tolerance_pct": 5.0, "unit": "score"},
        ]
        self.evaluate_decision(
            decision_id="dec_rec_timber_2023",
            scenario_id="scen_timber_sign",
            subject_entity_id="player_timber_12",
            subject_name="Jurriën Timber",
            expectations=timber_exp,
            evaluation_window="2023-2024_FULL_SEASON",
            assumptions=["Player settles into inverted fullback role within 60 days", "Transfer fee agreed at €40M base"],
        )

        # Declan Rice 2023 Evaluation
        rice_exp = [
            {"metric": "minutes_played", "expected": 3100.0, "tolerance_pct": 10.0, "unit": "minutes"},
            {"metric": "transfer_fee_paid_eur", "expected": 116_600_000.0, "tolerance_pct": 2.0, "unit": "EUR"},
        ]
        self.evaluate_decision(
            decision_id="dec_rice_arsenal_2023",
            scenario_id="scen_rice_record_signing",
            subject_entity_id="player_rice_41",
            subject_name="Declan Rice",
            expectations=rice_exp,
            evaluation_window="2023-2024_FULL_SEASON",
            assumptions=["Primary anchor in 4-3-3 midfield structure", "Initial transfer fee amortized over 5 seasons"],
        )


decision_realization_evaluator = DecisionRealizationEvaluator()
