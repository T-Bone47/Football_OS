"""Phase 14 — Decision Process Quality & Error Taxonomy Engine (§9, §11).

Evaluates the methodological and evidentiary rigor of a decision independent of football outcome:
  - Assesses: data sufficiency, sample size, competition coverage, calibration validity,
    confidence tiers, OOD status, evidence graph completeness, explicit assumptions,
    sensitivity analysis, and robustness stress-testing.
  - Process States:
    - WELL_SUPPORTED
    - SUPPORTED_WITH_LIMITATIONS
    - DATA_LIMITED
    - MODEL_LIMITED
    - SCENARIO_LIMITED
    - EVIDENCE_LIMITED
  - Multi-Label Error Taxonomy (§11):
    - DATA_ERROR, DATA_SPARSE, TEMPORAL_MISMATCH, MODEL_ERROR, CALIBRATION_ERROR,
      OOD_ERROR, ASSUMPTION_ERROR, SCENARIO_ERROR, EXECUTION_DIVERGENCE,
      UNOBSERVED_EXTERNAL_FACTOR, INSUFFICIENT_EVIDENCE.
    - Multiple factors can coexist without forcing single-cause attribution.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.phase14 import (
    DataSufficiencyStatus,
    DecisionProcessState,
    ErrorCategory,
)
from app.dev_fixtures import dev_seed_enabled


@dataclass
class ProcessQualityAudit:
    """Rigorous evaluation of decision process and evidentiary standards (§9)."""
    audit_id: str = field(default_factory=lambda: f"pqa_{uuid.uuid4().hex[:12]}")
    decision_id: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Evaluation Dimensions
    has_sufficient_data: bool = True
    sample_size_adequate: bool = True
    competition_coverage_valid: bool = True
    model_is_calibrated: bool = True
    confidence_tier_acceptable: bool = True
    ood_status_acceptable: bool = True
    evidence_graph_complete: bool = True
    assumptions_explicit: bool = True
    sensitivity_analysis_conducted: bool = True
    robustness_analysis_conducted: bool = True

    # Process State
    process_state: DecisionProcessState = DecisionProcessState.WELL_SUPPORTED
    quality_score_pct: float = 100.0

    # Identified Limitations & Findings
    limitations: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["process_state"] = self.process_state.value
        return data


@dataclass
class DivergenceDiagnostic:
    """Multi-label root divergence diagnosis using the canonical Error Taxonomy (§11)."""
    diagnostic_id: str = field(default_factory=lambda: f"diag_{uuid.uuid4().hex[:12]}")
    decision_id: str = ""
    scenario_id: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Multi-label error categorization (non-mutually exclusive)
    identified_categories: list[ErrorCategory] = field(default_factory=list)
    primary_category: ErrorCategory = ErrorCategory.INSUFFICIENT_EVIDENCE

    # Detailed non-causal evidentiary explanations
    category_explanations: dict[str, str] = field(default_factory=dict)
    remediation_recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["identified_categories"] = [c.value for c in self.identified_categories]
        data["primary_category"] = self.primary_category.value
        return data


class ProcessQualityEngine:
    """Evaluates process rigor and deterministically diagnoses divergence sources."""

    def __init__(self) -> None:
        self._audits: dict[str, ProcessQualityAudit] = {}
        self._diagnostics: dict[str, DivergenceDiagnostic] = {}
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_audits()

    def audit_decision_process(
        self,
        decision_id: str,
        has_sufficient_data: bool = True,
        sample_size_adequate: bool = True,
        competition_coverage_valid: bool = True,
        model_is_calibrated: bool = True,
        confidence_tier_acceptable: bool = True,
        ood_status_acceptable: bool = True,
        evidence_graph_complete: bool = True,
        assumptions_explicit: bool = True,
        sensitivity_analysis_conducted: bool = True,
        robustness_analysis_conducted: bool = True,
    ) -> ProcessQualityAudit:
        """Audits the methodological rigor of a decision record."""
        checks = [
            ("DATA", has_sufficient_data),
            ("SAMPLE_SIZE", sample_size_adequate),
            ("COMPETITION_COVERAGE", competition_coverage_valid),
            ("CALIBRATION", model_is_calibrated),
            ("CONFIDENCE", confidence_tier_acceptable),
            ("OOD", ood_status_acceptable),
            ("EVIDENCE_GRAPH", evidence_graph_complete),
            ("ASSUMPTIONS", assumptions_explicit),
            ("SENSITIVITY", sensitivity_analysis_conducted),
            ("ROBUSTNESS", robustness_analysis_conducted),
        ]

        passed_count = sum(1 for _, passed in checks if passed)
        quality_score = (passed_count / len(checks)) * 100.0
        limitations = []

        if not has_sufficient_data:
            limitations.append("Data volume below verified sufficiency thresholds.")
        if not sample_size_adequate:
            limitations.append("Sample size inadequate for high statistical power.")
        if not competition_coverage_valid:
            limitations.append("Competition readiness state is not PRODUCTION_READY.")
        if not model_is_calibrated:
            limitations.append("Model calibration metrics (ECE/MCE) exceed allowable boundaries.")
        if not ood_status_acceptable:
            limitations.append("Decision evaluated while target was Out-of-Distribution.")
        if not evidence_graph_complete:
            limitations.append("Evidence Graph lacks cryptographically verified lineage.")
        if not assumptions_explicit:
            limitations.append("Unstated or implicit priors detected in scenario definition.")
        if not sensitivity_analysis_conducted:
            limitations.append("Sensitivity analysis not recorded across fee/wage/contribution dimensions.")
        if not robustness_analysis_conducted:
            limitations.append("Scenario robustness stress-testing was omitted.")

        # Determine Process State
        if quality_score >= 90.0:
            state = DecisionProcessState.WELL_SUPPORTED
        elif quality_score >= 70.0:
            state = DecisionProcessState.SUPPORTED_WITH_LIMITATIONS
        elif not has_sufficient_data or not sample_size_adequate:
            state = DecisionProcessState.DATA_LIMITED
        elif not model_is_calibrated or not ood_status_acceptable:
            state = DecisionProcessState.MODEL_LIMITED
        elif not assumptions_explicit or not sensitivity_analysis_conducted:
            state = DecisionProcessState.SCENARIO_LIMITED
        else:
            state = DecisionProcessState.EVIDENCE_LIMITED

        findings = [
            f"Process quality score: {quality_score:.1f}% ({passed_count}/{len(checks)} standards satisfied).",
            f"Classified as {state.value}.",
            "Epistemic Note: Process quality assesses methodological and evidentiary compliance, not football outcome success.",
        ]

        audit = ProcessQualityAudit(
            decision_id=decision_id,
            has_sufficient_data=has_sufficient_data,
            sample_size_adequate=sample_size_adequate,
            competition_coverage_valid=competition_coverage_valid,
            model_is_calibrated=model_is_calibrated,
            confidence_tier_acceptable=confidence_tier_acceptable,
            ood_status_acceptable=ood_status_acceptable,
            evidence_graph_complete=evidence_graph_complete,
            assumptions_explicit=assumptions_explicit,
            sensitivity_analysis_conducted=sensitivity_analysis_conducted,
            robustness_analysis_conducted=robustness_analysis_conducted,
            process_state=state,
            quality_score_pct=round(quality_score, 1),
            limitations=limitations,
            findings=findings,
        )

        self._audits[decision_id] = audit
        return audit

    def diagnose_divergence(
        self,
        decision_id: str,
        scenario_id: str,
        metrics_diverged: list[str],
        data_status: DataSufficiencyStatus,
        is_ood: bool,
        calibration_error_observed: bool,
        assumption_drift_detected: bool,
        execution_change_detected: bool,
        unobserved_factors_noted: list[str] | None = None,
    ) -> DivergenceDiagnostic:
        """Classifies root divergence sources across the canonical Error Taxonomy (§11)."""
        categories: list[ErrorCategory] = []
        explanations: dict[str, str] = {}
        remediations: list[str] = []

        if data_status == DataSufficiencyStatus.INSUFFICIENT_DATA:
            categories.append(ErrorCategory.DATA_SPARSE)
            explanations["DATA_SPARSE"] = "Telemetry records insufficient to evaluate full decision window."
            remediations.append("Await additional match observation periods before drawing formal conclusions.")

        if is_ood:
            categories.append(ErrorCategory.OOD_ERROR)
            explanations["OOD_ERROR"] = "Target entity was evaluated in an Out-of-Distribution context."
            remediations.append("Flag OOD uncertainty in future scenario simulations involving cross-competition transfers.")

        if calibration_error_observed:
            categories.append(ErrorCategory.CALIBRATION_ERROR)
            explanations["CALIBRATION_ERROR"] = "Model probabilities exhibited empirical deviation from realized outcome frequencies."
            remediations.append("Evaluate recalibration using Platt scaling or isotonic regression in rolling window.")

        if assumption_drift_detected:
            categories.append(ErrorCategory.ASSUMPTION_ERROR)
            explanations["ASSUMPTION_ERROR"] = "Explicit scenario assumptions (e.g. role allocation, starting minutes) were not realized in practice."
            remediations.append("Review parameter bounds in scenario builder to avoid overly optimistic assumptions.")

        if execution_change_detected:
            categories.append(ErrorCategory.EXECUTION_DIVERGENCE)
            explanations["EXECUTION_DIVERGENCE"] = "Tactical deployment or squad management differed from simulated plan."
            remediations.append("Align simulation models more tightly with managerial rotation patterns.")

        if unobserved_factors_noted:
            categories.append(ErrorCategory.UNOBSERVED_EXTERNAL_FACTOR)
            explanations["UNOBSERVED_EXTERNAL_FACTOR"] = f"Unobserved real-world events occurred: {', '.join(unobserved_factors_noted)}."
            remediations.append("Incorporate availability risk modeling for sudden physical or context shocks.")

        if not categories:
            categories.append(ErrorCategory.INSUFFICIENT_EVIDENCE)
            explanations["INSUFFICIENT_EVIDENCE"] = "Divergence is minor or unexplained by recorded evidentiary signals."

        primary = categories[0]

        diagnostic = DivergenceDiagnostic(
            decision_id=decision_id,
            scenario_id=scenario_id,
            identified_categories=categories,
            primary_category=primary,
            category_explanations=explanations,
            remediation_recommendations=remediations,
        )

        self._diagnostics[decision_id] = diagnostic
        return diagnostic

    def get_process_audit(self, decision_id: str) -> ProcessQualityAudit | None:
        return self._audits.get(decision_id)

    def get_divergence_diagnostic(self, decision_id: str) -> DivergenceDiagnostic | None:
        return self._diagnostics.get(decision_id)

    def _seed_default_audits(self) -> None:
        """Seeds benchmark process audits and divergence diagnostics."""
        # Timber 2023 Process Audit
        self.audit_decision_process(
            decision_id="dec_rec_timber_2023",
            has_sufficient_data=True,
            sample_size_adequate=True,
            competition_coverage_valid=True,
            model_is_calibrated=True,
            confidence_tier_acceptable=True,
            ood_status_acceptable=True,
            evidence_graph_complete=True,
            assumptions_explicit=True,
            sensitivity_analysis_conducted=True,
            robustness_analysis_conducted=True,
        )
        self.diagnose_divergence(
            decision_id="dec_rec_timber_2023",
            scenario_id="scen_timber_sign",
            metrics_diverged=["minutes_played"],
            data_status=DataSufficiencyStatus.DATA_AVAILABLE,
            is_ood=False,
            calibration_error_observed=False,
            assumption_drift_detected=False,
            execution_change_detected=False,
            unobserved_factors_noted=["Severe knee ligament injury sustained on Matchday 1"],
        )

        # Rice 2023 Process Audit
        self.audit_decision_process(
            decision_id="dec_rice_arsenal_2023",
            has_sufficient_data=True,
            sample_size_adequate=True,
            competition_coverage_valid=True,
            model_is_calibrated=True,
            confidence_tier_acceptable=True,
            ood_status_acceptable=True,
            evidence_graph_complete=True,
            assumptions_explicit=True,
            sensitivity_analysis_conducted=True,
            robustness_analysis_conducted=True,
        )


process_quality_engine = ProcessQualityEngine()
