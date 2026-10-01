"""Pattern Discovery Engine for Phase 15 Global Football Research.

Discovers empirical candidates across 10 pattern families:
1. PLAYER_TRAJECTORY
2. ROLE_TRANSITION
3. TACTICAL_STRUCTURE
4. SQUAD_CONSTRUCTION
5. TRANSFER_MARKET
6. PLAYER_DEVELOPMENT
7. MATCH_CONTEXT
8. COMPETITION_STYLE
9. DECISION_OUTCOME
10. MODEL_ERROR

Rule: Emits PatternCandidate objects, NOT causal conclusions.
"""

from typing import Any
from app.phase15 import (
    DataSufficiencyStatus,
    EpistemicModality,
    GeneralizationDomain,
    PatternFamily,
)
from app.dev_fixtures import dev_seed_enabled
from app.phase15.causality_guardrail import CausalityGuardrail
from app.phase15.research_models import PatternCandidate


class PatternDiscoveryEngine:
    """Mines observational datasets for candidate patterns under strict epistemic governance."""

    def __init__(self, min_sample_threshold: int = 10) -> None:
        self.min_sample_threshold = min_sample_threshold
        self._candidates: dict[str, PatternCandidate] = {}

    def discover_pattern(
        self,
        pattern_id: str,
        family: PatternFamily,
        title: str,
        description: str,
        sample_size: int,
        temporal_scope: dict[str, str],
        competition_scope: list[str],
        effect_estimate: float,
        uncertainty: str,
        subgroup_breakdown: dict[str, Any] | None = None,
        confounder_warnings: list[str] | None = None,
        generalization_domain: GeneralizationDomain = GeneralizationDomain.IN_DOMAIN,
    ) -> PatternCandidate:
        """Evaluates sample sufficiency and constructs a candidate pattern without asserting causality."""
        # Cleanse language to ensure non-causal compliance
        clean_title = CausalityGuardrail.sanitize_text(title)
        clean_desc = CausalityGuardrail.sanitize_text(description)

        data_quality: DataSufficiencyStatus
        if sample_size == 0:
            data_quality = DataSufficiencyStatus.INSUFFICIENT_DATA
        elif sample_size < self.min_sample_threshold:
            data_quality = DataSufficiencyStatus.LOW_SAMPLE
        else:
            data_quality = DataSufficiencyStatus.DATA_AVAILABLE

        non_causal_statement = CausalityGuardrail.generate_statement(
            metric=f"{family.value} indicator (estimate: {effect_estimate:+.3f})",
            condition=f"cohort spanning {', '.join(competition_scope) or 'global'}",
            relationship="associated",
        )

        candidate = PatternCandidate(
            pattern_id=pattern_id,
            family=family,
            title=clean_title,
            description=clean_desc,
            sample_size=sample_size,
            temporal_scope=temporal_scope,
            competition_scope=competition_scope,
            effect_estimate=round(effect_estimate, 4),
            uncertainty=uncertainty,
            subgroup_breakdown=subgroup_breakdown or {},
            confounder_warnings=confounder_warnings or [
                "Uncontrolled team quality bias",
                "Minutes played threshold variance",
            ],
            data_quality_status=data_quality,
            generalization_domain=generalization_domain,
            epistemic_status=EpistemicModality.ANALYSIS,
            non_causal_statement=non_causal_statement,
        )

        self._candidates[pattern_id] = candidate
        return candidate

    def get_pattern(self, pattern_id: str) -> PatternCandidate:
        if pattern_id not in self._candidates:
            raise KeyError(f"PatternCandidate '{pattern_id}' not found.")
        return self._candidates[pattern_id]

    def list_patterns(self, family: PatternFamily | None = None) -> list[PatternCandidate]:
        patterns = list(self._candidates.values())
        if family:
            patterns = [p for p in patterns if p.family == family]
        return patterns


_GLOBAL_PATTERN_ENGINE: PatternDiscoveryEngine | None = None


def get_pattern_discovery_engine() -> PatternDiscoveryEngine:
    global _GLOBAL_PATTERN_ENGINE
    if _GLOBAL_PATTERN_ENGINE is None:
        _GLOBAL_PATTERN_ENGINE = PatternDiscoveryEngine()
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            # Seed representative candidate patterns across diverse families
            _GLOBAL_PATTERN_ENGINE.discover_pattern(
                pattern_id="pat_trajectory_u21_epl_breakout",
                family=PatternFamily.PLAYER_TRAJECTORY,
                title="Accelerated progression trajectory in U21 EPL wingers",
                description="U21 wingers with >1200 minutes exhibit sharp upward slope in progressive carries per 90.",
                sample_size=18,
                temporal_scope={"start": "2022-08-01", "end": "2024-05-30"},
                competition_scope=["EPL"],
                effect_estimate=0.42,
                uncertainty="Medium (95% CI: [+0.18, +0.66])",
                subgroup_breakdown={"top_half_clubs": {"N": 10, "slope": 0.49}, "bottom_half_clubs": {"N": 8, "slope": 0.33}},
            )
            _GLOBAL_PATTERN_ENGINE.discover_pattern(
                pattern_id="pat_transfer_fee_residual_bundesliga_to_epl",
                family=PatternFamily.TRANSFER_MARKET,
                title="Systematic positive valuation premium for Bundesliga -> EPL transfers",
                description="Transfers from Bundesliga to EPL show an empirical realized fee 15-25% above baseline modelled market valuation.",
                sample_size=24,
                temporal_scope={"start": "2021-07-01", "end": "2024-08-31"},
                competition_scope=["Bundesliga", "EPL"],
                effect_estimate=0.195,
                uncertainty="Low-to-Medium (N=24)",
                subgroup_breakdown={"attackers": {"N": 12, "residual": 0.23}, "midfielders": {"N": 8, "residual": 0.17}, "defenders": {"N": 4, "residual": 0.12}},
                confounder_warnings=["Premier League revenue disparity", "Contract length disparity"],
            )
            _GLOBAL_PATTERN_ENGINE.discover_pattern(
                pattern_id="pat_tactical_hybrid_back3_adaptation",
                family=PatternFamily.TACTICAL_STRUCTURE,
                title="Fullback to wide-CB transition in possession-heavy back-3",
                description="Athletic fullbacks transitioning to wide-CB in asymmetric back-3 maintain ball progression metrics while conceding fewer transitions.",
                sample_size=14,
                temporal_scope={"start": "2023-01-01", "end": "2024-05-30"},
                competition_scope=["Serie_A", "EPL", "La_Liga"],
                effect_estimate=0.28,
                uncertainty="Moderate sample uncertainty (N=14)",
                confounder_warnings=["Tactical manager bias", "Opposition defensive structure"],
            )
    return _GLOBAL_PATTERN_ENGINE
