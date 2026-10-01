"""Phase 12 — Emerging Player Detection Engine (§9).

Identifies young or transitioning players demonstrating multi-dimensional emergence:
  - Increasing minutes volume and starting share
  - Contribution percentile progression
  - Tactical fit alignment and role stabilization
  - Age-adjusted progression curve (U21 / U23 developmental window)
  - Market valuation lag relative to peer performance band

Rule: Dimensions are exposed independently without collapsing into an opaque composite score.
Status: EMERGING_OPPORTUNITY, WATCH, NO_SIGNAL.
Epistemic: Analytical evidence, not a guaranteed transfer or performance outcome.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from app.dev_fixtures import dev_seed_enabled


@dataclass
class EmergingPlayerOpportunity:
    """Multi-dimensional profile of an emerging player opportunity."""
    opportunity_id: str = field(default_factory=lambda: f"emg_{uuid.uuid4().hex[:12]}")
    player_id: str = ""
    player_name: str = ""
    age: int = 21
    current_club: str = ""
    competition_id: str = "GB-PL"
    position: str = "CB"
    primary_role: str = "Ball Playing Defender"

    # Multi-Dimensional Evidence Metrics (Exposed Independently)
    minutes_gain_pct: float = 0.0          # e.g. +38%
    contribution_gain_pts: float = 0.0     # e.g. +12 percentile points
    role_stability: str = "HIGH"           # HIGH, MODERATE, LOW
    tactical_fit_score: float = 85.0       # 0 - 100
    modelled_valuation_eur: float = 8_000_000.0
    comparable_range_eur: str = "€13M–€16M"
    valuation_lag_pct: float = 38.5        # Valuation below comparable midpoint

    # Synthesis
    status: str = "EMERGING_OPPORTUNITY"   # EMERGING_OPPORTUNITY, WATCH, NO_SIGNAL
    confidence: str = "HIGH"               # HIGH, MODERATE, LOW
    evidence: list[str] = field(default_factory=list)
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EmergingPlayerEngine:
    """Scans player trajectories to discover emerging player opportunities."""

    def __init__(self) -> None:
        self._opportunities: dict[str, EmergingPlayerOpportunity] = {}
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_opportunities()

    def _seed_default_opportunities(self) -> None:
        # Seed 1: Gonçalo Inácio (Sporting CP)
        seed_inacio = EmergingPlayerOpportunity(
            opportunity_id="emg_inacio_001",
            player_id="cand_inacio",
            player_name="Gonçalo Inácio",
            age=22,
            current_club="Sporting CP",
            competition_id="PT-PL",
            position="CB",
            primary_role="Ball Playing Defender",
            minutes_gain_pct=38.2,
            contribution_gain_pts=12.4,
            role_stability="HIGH",
            tactical_fit_score=86.2,
            modelled_valuation_eur=38_000_000.0,
            comparable_range_eur="€45M–€52M",
            valuation_lag_pct=21.6,
            status="EMERGING_OPPORTUNITY",
            confidence="HIGH",
            evidence=[
                "Minutes played increased by +38.2% in domestic & European competition.",
                "Contribution percentile progressed +12.4 points into top quintile (81.2).",
                "Modelled fee (€38M) lags comparable peer market band (€45M–€52M).",
                "High tactical role stability across both back-three and back-four defensive setups.",
            ],
        )
        self._opportunities[seed_inacio.player_id] = seed_inacio

        # Seed 2: Jarrad Branthwaite (Everton)
        seed_branthwaite = EmergingPlayerOpportunity(
            opportunity_id="emg_branthwaite_002",
            player_id="player_branthwaite_02",
            player_name="Jarrad Branthwaite",
            age=21,
            current_club="Everton",
            competition_id="GB-PL",
            position="CB",
            primary_role="Defensive Stopper",
            minutes_gain_pct=64.0,
            contribution_gain_pts=15.1,
            role_stability="HIGH",
            tactical_fit_score=83.5,
            modelled_valuation_eur=35_000_000.0,
            comparable_range_eur="€42M–€48M",
            valuation_lag_pct=22.2,
            status="EMERGING_OPPORTUNITY",
            confidence="HIGH",
            evidence=[
                "Regular starter status secured (+64% minutes expansion).",
                "Aerial duel win rate exceeding 68% in Premier League action.",
                "Valuation lags peer English U22 CB transfer benchmark.",
            ],
        )
        self._opportunities[seed_branthwaite.player_id] = seed_branthwaite

    def detect_emergence(
        self,
        player_id: str,
        player_name: str,
        age: int,
        current_club: str,
        competition_id: str,
        position: str,
        role: str,
        minutes_gain_pct: float,
        contribution_gain_pts: float,
        role_stability: str,
        tactical_fit_score: float,
        modelled_valuation_eur: float,
        comparable_range_eur: str,
        valuation_lag_pct: float,
    ) -> EmergingPlayerOpportunity:
        """Evaluates whether player meets multi-dimensional emergence thresholds."""
        evidence = []
        is_u23 = age <= 23
        strong_minutes = minutes_gain_pct >= 25.0
        strong_contrib = contribution_gain_pts >= 8.0

        if strong_minutes:
            evidence.append(f"Significant minutes expansion (+{minutes_gain_pct:.1f}%).")
        if strong_contrib:
            evidence.append(f"Contribution progression (+{contribution_gain_pts:.1f} pts).")
        if is_u23:
            evidence.append(f"Developmental age window (Age {age} <= 23).")
        if valuation_lag_pct >= 15.0:
            evidence.append(f"Modelled valuation lags comparable band by {valuation_lag_pct:.1f}%.")

        if is_u23 and strong_minutes and strong_contrib:
            status = "EMERGING_OPPORTUNITY"
            confidence = "HIGH"
        elif strong_minutes or strong_contrib:
            status = "WATCH"
            confidence = "MODERATE"
        else:
            status = "NO_SIGNAL"
            confidence = "LOW"

        opp = EmergingPlayerOpportunity(
            player_id=player_id,
            player_name=player_name,
            age=age,
            current_club=current_club,
            competition_id=competition_id,
            position=position,
            primary_role=role,
            minutes_gain_pct=minutes_gain_pct,
            contribution_gain_pts=contribution_gain_pts,
            role_stability=role_stability,
            tactical_fit_score=tactical_fit_score,
            modelled_valuation_eur=modelled_valuation_eur,
            comparable_range_eur=comparable_range_eur,
            valuation_lag_pct=valuation_lag_pct,
            status=status,
            confidence=confidence,
            evidence=evidence,
        )

        self._opportunities[player_id] = opp
        return opp

    def get_opportunity(self, player_id: str) -> EmergingPlayerOpportunity | None:
        return self._opportunities.get(player_id)

    def list_opportunities(self, status: str | None = None) -> list[EmergingPlayerOpportunity]:
        opps = list(self._opportunities.values())
        if status:
            opps = [o for o in opps if o.status == status]
        return opps


emerging_player_engine = EmergingPlayerEngine()
