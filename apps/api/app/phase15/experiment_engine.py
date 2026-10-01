"""Research Experiment Engine for Phase 15.

Governs versioned experiments linking:
- Hypothesis
- Dataset
- Cohort
- Feature candidate list
- Methodology
- Evaluation window
- Validation strategy
- Results & limitations

Produces deterministic experiment_hash for cryptographic reproducibility.
"""

import hashlib
import json
from typing import Any
from app.phase15.causality_guardrail import CausalityGuardrail
from app.phase15.research_models import ResearchExperiment, ResearchResult, ResearchValidation


class ExperimentEngine:
    """Manages creation, execution, hashing, and replay of research experiments."""

    def __init__(self) -> None:
        self._experiments: dict[str, ResearchExperiment] = {}

    def create_experiment(
        self,
        experiment_id: str,
        hypothesis_id: str,
        cohort_id: str,
        dataset_id: str,
        features_used: list[str],
        methodology: str,
        evaluation_window: dict[str, str],
        validation_strategy: str,
        sample_size: int = 0,
        competition_scope: list[str] | None = None,
        temporal_scope: dict[str, str] | None = None,
    ) -> ResearchExperiment:
        if experiment_id in self._experiments:
            raise ValueError(f"Experiment '{experiment_id}' already exists.")

        raw_sig = f"{experiment_id}:{hypothesis_id}:{cohort_id}:{dataset_id}:{sorted(features_used)}:{json.dumps(evaluation_window, sort_keys=True)}"
        exp_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()

        exp = ResearchExperiment(
            research_id=f"res_{experiment_id}",
            experiment_id=experiment_id,
            hypothesis_id=hypothesis_id,
            cohort_id=cohort_id,
            dataset_id=dataset_id,
            features_used=sorted(features_used),
            methodology=methodology,
            evaluation_window=evaluation_window,
            validation_strategy=validation_strategy,
            experiment_hash=exp_hash,
            is_completed=False,
            sample_size=sample_size,
            competition_scope=competition_scope or [],
            temporal_scope=temporal_scope or {},
        )

        self._experiments[experiment_id] = exp
        return exp

    def complete_experiment(
        self,
        experiment_id: str,
        effect_estimate: float,
        confidence_interval: tuple[float, float],
        p_value: float,
        subgroup_breakdown: dict[str, dict[str, Any]],
        summary_findings: list[str],
        validation: ResearchValidation | None = None,
        limitations: list[str] | None = None,
    ) -> ResearchExperiment:
        exp = self.get_experiment(experiment_id)
        if exp.is_completed:
            raise ValueError(f"Experiment '{experiment_id}' is already completed and immutable.")

        clean_findings = [CausalityGuardrail.sanitize_text(f) for f in summary_findings]
        non_causal = CausalityGuardrail.generate_statement(
            metric=f"experiment effect (estimate: {effect_estimate:+.3f})",
            condition=f"cohort {exp.cohort_id}",
            relationship="associated",
        )

        result = ResearchResult(
            result_id=f"res_{experiment_id}",
            effect_estimate=round(effect_estimate, 4),
            confidence_interval=(round(confidence_interval[0], 4), round(confidence_interval[1], 4)),
            p_value_or_posterior=round(p_value, 4),
            subgroup_breakdown=subgroup_breakdown,
            summary_findings=clean_findings,
            non_causal_statement=non_causal,
        )

        # Recompute final digest including results
        raw_final = f"{exp.experiment_hash}:{result.effect_estimate}:{result.p_value_or_posterior}:{json.dumps(subgroup_breakdown, sort_keys=True)}"
        final_hash = hashlib.sha256(raw_final.encode("utf-8")).hexdigest()

        exp.result = result
        exp.validation = validation
        exp.limitations = limitations or ["Observational selection bias", "Uncontrolled schedule density"]
        exp.experiment_hash = final_hash
        exp.is_completed = True

        return exp

    def get_experiment(self, experiment_id: str) -> ResearchExperiment:
        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment '{experiment_id}' not found.")
        return self._experiments[experiment_id]

    def list_experiments(self) -> list[ResearchExperiment]:
        return list(self._experiments.values())


_GLOBAL_EXPERIMENT_ENGINE: ExperimentEngine | None = None


def get_experiment_engine() -> ExperimentEngine:
    global _GLOBAL_EXPERIMENT_ENGINE
    if _GLOBAL_EXPERIMENT_ENGINE is None:
        _GLOBAL_EXPERIMENT_ENGINE = ExperimentEngine()
        # Seed realistic completed experiment
        exp1 = _GLOBAL_EXPERIMENT_ENGINE.create_experiment(
            experiment_id="exp_u23_retention_study",
            hypothesis_id="hypo_inverted_fb_retention",
            cohort_id="cohort_u23_midfielders_epl",
            dataset_id="ds_silver_canonical_2024",
            features_used=["press_resistance_index", "turnover_rate_p90", "progressive_pass_completion"],
            methodology="PROPENSITY_WEIGHTED_OBSERVATIONAL_COHORT",
            evaluation_window={"start": "2023-08-01", "end": "2024-05-30"},
            validation_strategy="TEMPORAL_HOLDOUT_Q4",
            sample_size=32,
            competition_scope=["EPL"],
        )
        _GLOBAL_EXPERIMENT_ENGINE.complete_experiment(
            experiment_id="exp_u23_retention_study",
            effect_estimate=0.245,
            confidence_interval=(0.112, 0.378),
            p_value=0.018,
            subgroup_breakdown={"top_6_clubs": {"N": 18, "effect": 0.28}, "rest_of_league": {"N": 14, "effect": 0.20}},
            summary_findings=["Higher ball retention observed among inverted fullback profiles when playing under pressure."],
        )
    return _GLOBAL_EXPERIMENT_ENGINE
