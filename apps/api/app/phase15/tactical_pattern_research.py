"""Tactical Pattern Research for Phase 15.

Strictly separates:
1. OBSERVED_TACTICAL_PATTERN: measured tracking, formation usage, and passing networks
2. MODELLED_TACTICAL_INTERPRETATION: tactical index algorithms, press resistance models
3. COUNTERFACTUAL_TACTICAL_SCENARIO: counterfactual simulations of unobserved lineups

Rule: Never merge observed structures with counterfactual scenarios.
Non-causal policy: Formations or tactical shifts are associated with, not causes of, outcomes.
"""

from typing import Any
from pydantic import BaseModel, Field
from app.phase15.causality_guardrail import CausalityGuardrail
from app.dev_fixtures import dev_seed_enabled


class ObservedTacticalPattern(BaseModel):
    pattern_id: str
    team_id: str
    competition: str
    season: str
    matches_observed: int
    primary_shape: str  # e.g., "4-3-3"
    in_possession_structure: str  # e.g., "3-2-5"
    out_of_possession_structure: str  # e.g., "4-4-2"
    measured_width_meters: float
    high_press_line_meters: float
    modality: str = "OBSERVED"


class ModelledTacticalInterpretation(BaseModel):
    pattern_id: str
    model_name: str
    model_version: str
    progression_channel_bias: dict[str, float]  # left, central, right
    counter_press_intensity_index: float
    box_occupation_density: float
    modality: str = "MODELLED"


class CounterfactualTacticalScenarioRef(BaseModel):
    scenario_id: str
    simulated_formation: str
    simulated_variation: str
    modality: str = "COUNTERFACTUAL"


class TacticalResearchReport(BaseModel):
    report_id: str
    team_id: str
    observed_pattern: ObservedTacticalPattern
    modelled_interpretation: ModelledTacticalInterpretation
    counterfactual_scenarios: list[CounterfactualTacticalScenarioRef] = Field(default_factory=list)
    non_causal_statement: str
    epistemic_audit_passed: bool = True


class TacticalPatternResearchEngine:
    """Manages observed, modelled, and counterfactual tactical research records."""

    def __init__(self) -> None:
        self._reports: dict[str, TacticalResearchReport] = {}

    def record_tactical_research(
        self,
        team_id: str,
        competition: str,
        season: str,
        matches_observed: int,
        primary_shape: str,
        in_possession_structure: str,
        out_of_possession_structure: str,
        measured_width: float,
        high_press_line: float,
        progression_bias: dict[str, float],
        counter_press_index: float,
        box_density: float,
        counterfactuals: list[dict[str, str]] | None = None,
    ) -> TacticalResearchReport:
        report_id = f"tac_res_{team_id}_{season.replace('/', '_')}"

        observed = ObservedTacticalPattern(
            pattern_id=f"obs_{report_id}",
            team_id=team_id,
            competition=competition,
            season=season,
            matches_observed=matches_observed,
            primary_shape=primary_shape,
            in_possession_structure=in_possession_structure,
            out_of_possession_structure=out_of_possession_structure,
            measured_width_meters=measured_width,
            high_press_line_meters=high_press_line,
        )

        modelled = ModelledTacticalInterpretation(
            pattern_id=f"mod_{report_id}",
            model_name="TacticalStructureModel",
            model_version="v15.0",
            progression_channel_bias=progression_bias,
            counter_press_intensity_index=counter_press_index,
            box_occupation_density=box_density,
        )

        cfs = [
            CounterfactualTacticalScenarioRef(
                scenario_id=cf["scenario_id"],
                simulated_formation=cf["simulated_formation"],
                simulated_variation=cf["simulated_variation"],
            )
            for cf in (counterfactuals or [])
        ]

        non_causal_statement = CausalityGuardrail.generate_statement(
            metric=f"tactical organization ({in_possession_structure} / {out_of_possession_structure})",
            condition=f"{matches_observed} observed matches in {competition}",
            relationship="aligned",
        )

        report = TacticalResearchReport(
            report_id=report_id,
            team_id=team_id,
            observed_pattern=observed,
            modelled_interpretation=modelled,
            counterfactual_scenarios=cfs,
            non_causal_statement=non_causal_statement,
        )

        self._reports[report_id] = report
        return report

    def get_report(self, report_id: str) -> TacticalResearchReport:
        if report_id not in self._reports:
            raise KeyError(f"Tactical research report '{report_id}' not found.")
        return self._reports[report_id]

    def list_reports(self) -> list[TacticalResearchReport]:
        return list(self._reports.values())


_GLOBAL_TACTICAL_ENGINE: TacticalPatternResearchEngine | None = None


def get_tactical_pattern_engine() -> TacticalPatternResearchEngine:
    global _GLOBAL_TACTICAL_ENGINE
    if _GLOBAL_TACTICAL_ENGINE is None:
        _GLOBAL_TACTICAL_ENGINE = TacticalPatternResearchEngine()
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            _GLOBAL_TACTICAL_ENGINE.record_tactical_research(
                team_id="arsenal_fc",
                competition="EPL",
                season="2023/2024",
                matches_observed=38,
                primary_shape="4-3-3",
                in_possession_structure="3-2-5",
                out_of_possession_structure="4-4-2",
                measured_width=52.4,
                high_press_line=48.2,
                progression_bias={"left": 0.38, "central": 0.22, "right": 0.40},
                counter_press_index=0.88,
                box_density=0.74,
                counterfactuals=[
                    {"scenario_id": "scen_343_switch", "simulated_formation": "3-4-3", "simulated_variation": "symmetric_wingbacks"}
                ],
            )
    return _GLOBAL_TACTICAL_ENGINE
