"""Hypothesis Governance and Independent Validation Engine for Phase 15.

Governs the research lifecycle:
DISCOVERED -> HYPOTHESIS -> TESTING -> VALIDATED / REJECTED / INSUFFICIENT_EVIDENCE -> PRODUCTION_CANDIDATE -> PROMOTED

Requires:
- Independent cohort validation
- Temporal holdout audit
- Leakage detection
- Non-causal phrasing
"""

from typing import Any
from app.phase15 import (
    EpistemicModality,
    HypothesisValidationResult,
    ResearchLifecycleState,
)
from app.dev_fixtures import dev_seed_enabled
from app.phase15.causality_guardrail import CausalityGuardrail
from app.phase15.research_models import ResearchHypothesis, ResearchValidation


class HypothesisGovernanceEngine:
    """Manages creation, lifecycle updates, and independent validation of hypotheses."""

    def __init__(self, min_validation_sample: int = 20) -> None:
        self.min_validation_sample = min_validation_sample
        self._hypotheses: dict[str, ResearchHypothesis] = {}
        self._validations: dict[str, list[ResearchValidation]] = {}

    def create_hypothesis(
        self,
        hypothesis_id: str,
        statement: str,
        source_patterns: list[str],
        supporting_observations: list[dict[str, Any]],
        sample_size: int,
        affected_competitions: list[str],
        affected_seasons: list[str],
        confounders: list[str] | None = None,
        question_id: str | None = None,
    ) -> ResearchHypothesis:
        """Constructs a research hypothesis ensuring non-causal compliance."""
        clean_statement = CausalityGuardrail.sanitize_text(statement)

        hypo = ResearchHypothesis(
            research_id=f"res_{hypothesis_id}",
            hypothesis_id=hypothesis_id,
            question_id=question_id,
            statement=clean_statement,
            epistemic_status=EpistemicModality.HYPOTHESIS,
            lifecycle_state=ResearchLifecycleState.HYPOTHESIS,
            source_patterns=source_patterns,
            supporting_observations=supporting_observations,
            sample_size=sample_size,
            affected_competitions=affected_competitions,
            affected_seasons=affected_seasons,
            confounders=confounders or ["Sample selection bias", "Role taxonomy variation"],
            uncertainty_description="Pre-validation hypothesis: requires independent holdout cohort testing.",
            is_causal_claim=False,
        )

        self._hypotheses[hypothesis_id] = hypo
        self._validations[hypothesis_id] = []
        return hypo

    def validate_hypothesis(
        self,
        hypothesis_id: str,
        validation_id: str,
        methodology: str,  # INDEPENDENT_COHORT, TEMPORAL_HOLDOUT, COMPETITION_HOLDOUT, NEGATIVE_CONTROL
        holdout_sample_size: int,
        holdout_window: dict[str, str],
        metrics: dict[str, float],
        leakage_detected: bool = False,
    ) -> ResearchValidation:
        """Executes independent validation against an isolated holdout cohort."""
        hypo = self.get_hypothesis(hypothesis_id)
        hypo.lifecycle_state = ResearchLifecycleState.TESTING

        limitations: list[str] = []
        res: HypothesisValidationResult

        if leakage_detected:
            res = HypothesisValidationResult.NOT_SUPPORTED
            limitations.append("Temporal or feature leakage detected in validation cohort; result disqualified.")
            hypo.lifecycle_state = ResearchLifecycleState.REJECTED
        elif holdout_sample_size < self.min_validation_sample:
            res = HypothesisValidationResult.INSUFFICIENT_EVIDENCE
            limitations.append(f"Holdout sample size (N={holdout_sample_size}) below threshold ({self.min_validation_sample}).")
            hypo.lifecycle_state = ResearchLifecycleState.INSUFFICIENT_EVIDENCE
        else:
            effect = metrics.get("effect_size", 0.0)
            p_val = metrics.get("p_value", 0.50)

            if effect >= 0.20 and p_val <= 0.05:
                res = HypothesisValidationResult.SUPPORTED
                hypo.lifecycle_state = ResearchLifecycleState.VALIDATED
            elif effect >= 0.10:
                res = HypothesisValidationResult.PARTIALLY_SUPPORTED
                hypo.lifecycle_state = ResearchLifecycleState.VALIDATED
                limitations.append("Effect size is modest or marginally statistically significant.")
            else:
                res = HypothesisValidationResult.NOT_SUPPORTED
                hypo.lifecycle_state = ResearchLifecycleState.REJECTED
                limitations.append("Independent holdout failed to replicate candidate effect.")

        non_causal = CausalityGuardrail.generate_statement(
            metric=f"hypothesis statement",
            condition=f"independent holdout ({methodology}, N={holdout_sample_size})",
            relationship="aligned" if res in (HypothesisValidationResult.SUPPORTED, HypothesisValidationResult.PARTIALLY_SUPPORTED) else "diverged",
        )

        validation = ResearchValidation(
            validation_id=validation_id,
            methodology=methodology,
            sample_size=holdout_sample_size,
            holdout_window=holdout_window,
            result=res,
            metrics=metrics,
            leakage_audit_passed=(not leakage_detected),
            limitations=limitations,
            non_causal_statement=non_causal,
        )

        self._validations[hypothesis_id].append(validation)
        return validation

    def get_hypothesis(self, hypothesis_id: str) -> ResearchHypothesis:
        if hypothesis_id not in self._hypotheses:
            raise KeyError(f"Hypothesis '{hypothesis_id}' not found.")
        return self._hypotheses[hypothesis_id]

    def list_hypotheses(self, state: ResearchLifecycleState | None = None) -> list[ResearchHypothesis]:
        items = list(self._hypotheses.values())
        if state:
            items = [h for h in items if h.lifecycle_state == state]
        return items

    def get_validations(self, hypothesis_id: str) -> list[ResearchValidation]:
        return self._validations.get(hypothesis_id, [])


_GLOBAL_HYPOTHESIS_ENGINE: HypothesisGovernanceEngine | None = None


def get_hypothesis_engine() -> HypothesisGovernanceEngine:
    global _GLOBAL_HYPOTHESIS_ENGINE
    if _GLOBAL_HYPOTHESIS_ENGINE is None:
        _GLOBAL_HYPOTHESIS_ENGINE = HypothesisGovernanceEngine()
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            # Seed realistic hypotheses
            h1 = _GLOBAL_HYPOTHESIS_ENGINE.create_hypothesis(
                hypothesis_id="hypo_inverted_fb_retention",
                statement="Players transitioning from traditional FB to Inverted Midfield roles show consistent ball retention under high pressure.",
                source_patterns=["pat_tactical_hybrid_back3_adaptation"],
                supporting_observations=[{"player": "John Stones", "metric": "retention", "val": 0.91}],
                sample_size=18,
                affected_competitions=["EPL", "La_Liga"],
                affected_seasons=["2022/2023", "2023/2024"],
            )
            # Validate h1
            _GLOBAL_HYPOTHESIS_ENGINE.validate_hypothesis(
                hypothesis_id="hypo_inverted_fb_retention",
                validation_id="val_h1_temporal_holdout",
                methodology="TEMPORAL_HOLDOUT",
                holdout_sample_size=24,
                holdout_window={"start": "2024-01-01", "end": "2024-05-30"},
                metrics={"effect_size": 0.26, "p_value": 0.02},
                leakage_detected=False,
            )
    return _GLOBAL_HYPOTHESIS_ENGINE
