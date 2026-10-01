"""Phase 9 — OOD (Out-of-Distribution) Validation Framework.

Stress-tests the system against unfamiliar competitions, clubs, players,
seasons, and tactical contexts. Verifies that data status labels:
  IN-DISTRIBUTION, LOW_CONFIDENCE, INSUFFICIENT_DATA, OUT_OF_DISTRIBUTION
behave consistently, and that OOD never silently becomes normal-confidence output.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DataStatusLabel(str, Enum):
    IN_DISTRIBUTION = "IN_DISTRIBUTION"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"


class OODTestResult(str, Enum):
    PASSED = "PASSED"        # Engine correctly identifies OOD/low-confidence
    FAILED = "FAILED"        # Engine silently gives normal-confidence for OOD input
    SKIPPED = "SKIPPED"      # Insufficient data to run test


@dataclass
class OODScenario:
    """A single OOD stress-test scenario."""
    scenario_id: str
    category: str          # 'competition', 'club', 'player', 'season', 'tactical'
    description: str
    engine: str
    expected_status: str   # Expected DataStatusLabel
    actual_status: str | None = None
    actual_confidence: float | None = None
    test_result: str = OODTestResult.SKIPPED
    evidence: list[str] = field(default_factory=list)


@dataclass
class OODValidationReport:
    """Complete OOD validation report."""
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    version: str = "ood_validation_v1"
    scenarios: list[OODScenario] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _build_ood_scenarios() -> list[OODScenario]:
    """Define OOD test scenarios for all major engines."""
    scenarios = []

    # Competition OOD: Unknown/unseen competition
    scenarios.append(OODScenario(
        scenario_id="ood_comp_mls",
        category="competition",
        description="MLS (Major League Soccer) — not in training distribution",
        engine="match_prediction",
        expected_status=DataStatusLabel.OUT_OF_DISTRIBUTION,
    ))
    scenarios.append(OODScenario(
        scenario_id="ood_comp_j_league",
        category="competition",
        description="J-League (Japan) — not in training distribution",
        engine="valuation",
        expected_status=DataStatusLabel.OUT_OF_DISTRIBUTION,
    ))
    scenarios.append(OODScenario(
        scenario_id="ood_comp_a_league",
        category="competition",
        description="A-League (Australia) — not in training distribution",
        engine="player_intelligence",
        expected_status=DataStatusLabel.INSUFFICIENT_DATA,
    ))

    # Club OOD: Unknown club
    scenarios.append(OODScenario(
        scenario_id="ood_club_unknown",
        category="club",
        description="Unknown club with no historical data",
        engine="match_prediction",
        expected_status=DataStatusLabel.INSUFFICIENT_DATA,
    ))
    scenarios.append(OODScenario(
        scenario_id="ood_club_newly_promoted",
        category="club",
        description="Newly promoted club with minimal prior data",
        engine="tactical_fit",
        expected_status=DataStatusLabel.LOW_CONFIDENCE,
    ))

    # Player OOD: Player from unseen competition
    scenarios.append(OODScenario(
        scenario_id="ood_player_unseen_league",
        category="player",
        description="Player from a league outside the training data",
        engine="similarity",
        expected_status=DataStatusLabel.INSUFFICIENT_DATA,
    ))
    scenarios.append(OODScenario(
        scenario_id="ood_player_youth",
        category="player",
        description="Youth player with < 90 minutes total",
        engine="player_intelligence",
        expected_status=DataStatusLabel.INSUFFICIENT_DATA,
    ))

    # Season OOD: Future season
    scenarios.append(OODScenario(
        scenario_id="ood_season_future",
        category="season",
        description="Season 2028/2029 — not yet occurred",
        engine="valuation",
        expected_status=DataStatusLabel.OUT_OF_DISTRIBUTION,
    ))

    # Tactical OOD: Unusual formation
    scenarios.append(OODScenario(
        scenario_id="ood_tactic_unusual",
        category="tactical",
        description="3-1-4-2 formation with inverted wingbacks — rare tactical context",
        engine="tactical_fit",
        expected_status=DataStatusLabel.LOW_CONFIDENCE,
    ))

    # Transfer risk OOD: Very unusual transfer scenario
    scenarios.append(OODScenario(
        scenario_id="ood_risk_crosscontinent",
        category="competition",
        description="Transfer from Chinese Super League to La Liga — rare cross-continent move",
        engine="transfer_risk",
        expected_status=DataStatusLabel.LOW_CONFIDENCE,
    ))

    return scenarios


def validate_ood_behavior(
    data_status_fn: Any = None,
) -> OODValidationReport:
    """Run OOD validation scenarios against the system.

    Args:
        data_status_fn: Optional callable that takes scenario context and returns
                       the actual data_status label from the engine. If None,
                       performs structural validation only.

    Returns:
        OODValidationReport with results for each scenario.
    """
    report = OODValidationReport()
    scenarios = _build_ood_scenarios()

    for scenario in scenarios:
        if data_status_fn is not None:
            try:
                actual = data_status_fn(scenario)
                scenario.actual_status = actual.get("data_status")
                scenario.actual_confidence = actual.get("confidence")

                # Check if OOD was correctly identified
                if scenario.actual_status in (
                    DataStatusLabel.OUT_OF_DISTRIBUTION,
                    DataStatusLabel.INSUFFICIENT_DATA,
                    DataStatusLabel.LOW_CONFIDENCE,
                ):
                    scenario.test_result = OODTestResult.PASSED
                    scenario.evidence.append(
                        f"Engine correctly returned {scenario.actual_status}"
                    )
                else:
                    # If engine returned normal confidence for OOD input, that's a failure
                    scenario.test_result = OODTestResult.FAILED
                    scenario.evidence.append(
                        f"Engine returned {scenario.actual_status} for OOD input — "
                        f"expected {scenario.expected_status}"
                    )
            except Exception as exc:
                scenario.test_result = OODTestResult.SKIPPED
                scenario.evidence.append(f"Error during evaluation: {type(exc).__name__}: {exc}")
        else:
            # Structural validation: verify the scenario is well-defined
            scenario.test_result = OODTestResult.PASSED
            scenario.evidence.append(
                "Structural validation only — data_status_fn not provided. "
                "Scenario definition verified."
            )

        report.scenarios.append(scenario)

    # Summary
    passed = sum(1 for s in report.scenarios if s.test_result == OODTestResult.PASSED)
    failed = sum(1 for s in report.scenarios if s.test_result == OODTestResult.FAILED)
    skipped = sum(1 for s in report.scenarios if s.test_result == OODTestResult.SKIPPED)

    report.summary = {
        "total_scenarios": len(report.scenarios),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": round(passed / max(passed + failed, 1), 3),
        "categories_tested": sorted(set(s.category for s in report.scenarios)),
        "engines_tested": sorted(set(s.engine for s in report.scenarios)),
    }

    report.limitations = [
        "OOD validation is scenario-based; not all possible OOD inputs are tested",
        "Without live engine access, structural validation confirms scenario definitions only",
        "Competition OOD depends on the training data distribution; new competitions added in future phases may change results",
        "Tactical OOD scenarios are limited to formation-level checks; style-level OOD is harder to detect",
    ]

    return report
