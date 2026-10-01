"""Phase 13 — Budget Allocation, Squad Depth & Academy Integration Simulator (§11, §12, §13, §17).

Provides:
  1. Squad Depth Simulation (§11):
     Stress-tests squad against injury absence, suspensions, rotation, and fixture congestion.
     States: SOLID, ADEQUATE, THIN, CRITICAL_GAP.

  2. Fixture Congestion Modeling (§12):
     Evaluates domestic-only vs domestic + European campaign minute requirements.

  3. Budget Allocation Across 8 Pitch Zones (§13):
     CB, FB, DM, CM, AM, W, ST, GK. Evaluates trade-offs without forcing a single ranking.

  4. Academy Integration Pathways (§17):
     Evaluates youth readiness: NOT_READY, DEVELOPMENTAL, ROTATION_READY, SQUAD_READY.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.phase13 import AcademyReadinessState, SquadDepthState


@dataclass
class PositionDepthReport:
    """Depth status for a specific pitch position group."""
    position: str
    primary_starter: str
    secondary_backup: str
    tertiary_reserve: str | None = None
    starter_minutes_share_pct: float = 78.5
    depth_state: SquadDepthState = SquadDepthState.SOLID
    vulnerability_notes: list[str] = field(default_factory=list)


@dataclass
class PositionCoverageSummary:
    position_group: str
    depth_state: str
    starters_count: int
    primary_reserves_count: int
    academy_backups_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SquadDepthStressTestResult:
    """Outcome of stress-testing squad roster under hypothetical congestion scenarios."""
    test_id: str = field(default_factory=lambda: f"depth_{uuid.uuid4().hex[:12]}")
    fixture_schedule_type: str = "DOMESTIC_PLUS_EUROPE"  # DOMESTIC_ONLY, DOMESTIC_PLUS_EUROPE, CUP_CONGESTION
    simulated_match_count: int = 54
    total_minutes_required: int = 53_460  # 11 players * 90 mins * 54 matches
    positions_analyzed: list[PositionDepthReport] = field(default_factory=list)
    overall_depth_state: SquadDepthState = SquadDepthState.ADEQUATE
    overall_depth_rating: float = 84.5
    simulated_absences: list[str] = field(default_factory=list)
    critical_vulnerabilities: list[str] = field(default_factory=list)
    critical_positions: list[str] = field(default_factory=list)
    position_coverages: list[PositionCoverageSummary] = field(default_factory=list)
    simulated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def depth_state(self) -> str:
        return self.overall_depth_state.value if hasattr(self.overall_depth_state, "value") else str(self.overall_depth_state)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "fixture_schedule_type": self.fixture_schedule_type,
            "simulated_match_count": self.simulated_match_count,
            "total_minutes_required": self.total_minutes_required,
            "overall_depth_state": self.depth_state,
            "depth_state": self.depth_state,
            "overall_depth_rating": self.overall_depth_rating,
            "simulated_absences": self.simulated_absences,
            "critical_vulnerabilities": self.critical_vulnerabilities,
            "critical_positions": self.critical_positions,
            "position_coverages": [p.to_dict() for p in self.position_coverages],
            "positions_analyzed": [asdict(p) for p in self.positions_analyzed],
            "simulated_at": self.simulated_at,
        }


@dataclass
class BudgetAllocationStrategy:
    """Simulated capital allocation across 8 pitch zones."""
    allocation_id: str = field(default_factory=lambda: f"alloc_{uuid.uuid4().hex[:12]}")
    total_budget_eur: float = 80_000_000.0
    zone_allocations_eur: dict[str, float] = field(
        default_factory=lambda: {
            "CB": 40_000_000.0,
            "FB": 10_000_000.0,
            "DM": 15_000_000.0,
            "CM": 5_000_000.0,
            "AM": 0.0,
            "W": 10_000_000.0,
            "ST": 0.0,
            "GK": 0.0,
        }
    )
    squad_gap_coverage_score: float = 88.0
    tactical_depth_score: float = 85.5
    financial_sustainability_rating: str = "HIGH"
    trade_off_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AcademyProspectEvaluation:
    """Empirical assessment of an academy player's tactical readiness."""
    prospect_id: str
    name: str
    age: int
    position: str
    academy_minutes_recorded: int
    first_team_minutes: int
    contribution_percentile: float
    tactical_fit_score: float
    readiness_state: AcademyReadinessState = AcademyReadinessState.ROTATION_READY
    justification: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["readiness_state"] = self.readiness_state.value
        return data


class BudgetAndDepthSimulator:
    """Simulates roster depth, fixture congestion, budget division, and academy integration."""

    def stress_test_depth(
        self,
        schedule_type: str = "DOMESTIC_PLUS_EUROPE",
        injuries: list[str] | None = None,
    ) -> SquadDepthStressTestResult:
        """Simulates fixture congestion with optional injury absences."""
        injured_set = set(injuries or [])

        # Positions Depth breakdown
        cb_backup = "Jakub Kiwior" if "p_kiwior" not in injured_set else "Ayden Heaven (Academy)"
        cb_state = SquadDepthState.SOLID if "p_saliba" not in injured_set else SquadDepthState.THIN

        positions = [
            PositionDepthReport("CB", "William Saliba", "Gabriel Magalhães", cb_backup, 74.0, cb_state),
            PositionDepthReport("RB", "Ben White", "Jurriën Timber", None, 72.0, SquadDepthState.SOLID),
            PositionDepthReport("LB", "Jurriën Timber", "Jakub Kiwior", None, 68.0, SquadDepthState.SOLID),
            PositionDepthReport("DM", "Declan Rice", "Thomas Partey", "Jorginho", 81.0, SquadDepthState.SOLID),
            PositionDepthReport("AM", "Martin Ødegaard", "Fabio Vieira", "Ethan Nwaneri", 84.0, SquadDepthState.ADEQUATE),
            PositionDepthReport("RW", "Bukayo Saka", "Reiss Nelson", None, 88.0, SquadDepthState.THIN, ["High minutes overload on starter; limited natural backup."]),
            PositionDepthReport("LW", "Gabriel Martinelli", "Leandro Trossard", None, 65.0, SquadDepthState.SOLID),
            PositionDepthReport("CF", "Kai Havertz", "Gabriel Jesus", None, 62.0, SquadDepthState.SOLID),
            PositionDepthReport("GK", "David Raya", "Neto", None, 92.0, SquadDepthState.ADEQUATE),
        ]

        critical = [p.position for p in positions if p.depth_state in [SquadDepthState.THIN, SquadDepthState.CRITICAL_GAP]]

        return SquadDepthStressTestResult(
            fixture_schedule_type=schedule_type,
            simulated_match_count=54 if schedule_type == "DOMESTIC_PLUS_EUROPE" else 38,
            total_minutes_required=53_460 if schedule_type == "DOMESTIC_PLUS_EUROPE" else 37_620,
            positions_analyzed=positions,
            overall_depth_state=SquadDepthState.ADEQUATE if len(critical) <= 2 else SquadDepthState.THIN,
            critical_positions=critical,
        )

    def simulate_depth_stress(
        self,
        club_id: str = "arsenal_fc",
        congestion_mode: str = "DOMESTIC_LEAGUE",
        additional_absences: list[str] | None = None,
    ) -> SquadDepthStressTestResult:
        """Simulates depth and fixture congestion vulnerabilities."""
        absences = additional_absences or []
        is_congested = "EUROPE" in congestion_mode or "CONGESTION" in congestion_mode or "SEVERE" in congestion_mode
        base_rating = 82.0 if is_congested else 88.5
        rating = max(55.0, base_rating - len(absences) * 8.5)

        if rating >= 85.0:
            state = SquadDepthState.SOLID
        elif rating >= 75.0:
            state = SquadDepthState.ADEQUATE
        elif rating >= 65.0:
            state = SquadDepthState.THIN
        else:
            state = SquadDepthState.CRITICAL_GAP

        vulnerabilities = []
        if is_congested:
            vulnerabilities.append("Right Wing: High minute load on Saka with limited natural rotation options.")
        if any("partey" in a.lower() or "rice" in a.lower() for a in absences):
            vulnerabilities.append("Central Midfield: Single point of failure at Lone Pivot.")
        if len(absences) >= 2:
            vulnerabilities.append("Rotational squad strain: Multiple concurrent starter absences violate depth tolerance.")

        coverages = [
            PositionCoverageSummary("Central Defence", "SOLID" if len(absences) < 2 else "THIN", 2, 2, 1),
            PositionCoverageSummary("Fullbacks", "SOLID", 2, 2, 0),
            PositionCoverageSummary("Central Midfield", "THIN" if any("partey" in a.lower() for a in absences) else "SOLID", 3, 2, 1),
            PositionCoverageSummary("Attackers", "ADEQUATE", 3, 2, 1),
        ]

        return SquadDepthStressTestResult(
            fixture_schedule_type=congestion_mode,
            simulated_match_count=54 if is_congested else 38,
            total_minutes_required=53_460 if is_congested else 37_620,
            overall_depth_state=state,
            overall_depth_rating=rating,
            simulated_absences=absences,
            critical_vulnerabilities=vulnerabilities,
            critical_positions=[v.split(":")[0] for v in vulnerabilities],
            position_coverages=coverages,
        )

    def allocate_budget(
        self,
        total_budget_eur: float,
        target_positions: list[str],
    ) -> list[BudgetAllocationStrategy]:
        """Generates multiple feasible budget allocation strategies across pitch zones."""
        # Strategy 1: Spine Priority (CB + DM focus)
        s1 = BudgetAllocationStrategy(
            total_budget_eur=total_budget_eur,
            zone_allocations_eur={"CB": total_budget_eur * 0.50, "DM": total_budget_eur * 0.35, "FB": total_budget_eur * 0.15},
            squad_gap_coverage_score=89.5,
            tactical_depth_score=86.0,
            financial_sustainability_rating="HIGH",
            trade_off_notes=["Invests 85% of funds into central defensive spine; leaves attacking wing depth to academy/internal rotation."],
        )

        # Strategy 2: Balanced Allocation
        s2 = BudgetAllocationStrategy(
            total_budget_eur=total_budget_eur,
            zone_allocations_eur={"CB": total_budget_eur * 0.40, "W": total_budget_eur * 0.30, "FB": total_budget_eur * 0.30},
            squad_gap_coverage_score=84.0,
            tactical_depth_score=88.5,
            financial_sustainability_rating="HIGH",
            trade_off_notes=["Distributes funds across CB, Wing, and Fullback cover; addresses Saka minutes overload."],
        )

        return [s1, s2]

    def evaluate_academy_prospect(
        self,
        prospect_id: str,
        name: str,
        age: int,
        position: str,
        academy_minutes: int,
        first_team_minutes: int,
        contribution_percentile: float,
        tactical_fit_score: float,
    ) -> AcademyProspectEvaluation:
        """Evaluates academy player readiness without inferring potential purely from age."""
        if first_team_minutes >= 450:
            readiness = AcademyReadinessState.SQUAD_READY
        elif first_team_minutes >= 90 or (academy_minutes >= 1200 and tactical_fit_score >= 80.0):
            readiness = AcademyReadinessState.ROTATION_READY
        elif academy_minutes >= 600:
            readiness = AcademyReadinessState.DEVELOPMENTAL
        else:
            readiness = AcademyReadinessState.NOT_READY

        return AcademyProspectEvaluation(
            prospect_id=prospect_id,
            name=name,
            age=age,
            position=position,
            academy_minutes_recorded=academy_minutes,
            first_team_minutes=first_team_minutes,
            contribution_percentile=contribution_percentile,
            tactical_fit_score=tactical_fit_score,
            readiness_state=readiness,
            justification=[
                f"Recorded {academy_minutes} U21 academy minutes and {first_team_minutes} senior first-team minutes.",
                f"Tactical fit score evaluated at {tactical_fit_score}/100.",
            ],
        )


BudgetDepthSimulator = BudgetAndDepthSimulator
budget_depth_simulator = BudgetAndDepthSimulator()
