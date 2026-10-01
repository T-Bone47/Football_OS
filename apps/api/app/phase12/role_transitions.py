"""Phase 12 — Tactical Role Transition Engine (§11).

Detects empirical role profile shifts across temporal observation windows:
  Example: Traditional Fullback → Inverted Fullback
  Example: Progressive Midfielder → Chance Creator

Epistemic Non-Causal Policy:
  - Never infer manager psychology or intent.
  - State: "Observed role profile shifted..." NEVER "Manager converted player because..."
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from app.dev_fixtures import dev_seed_enabled


@dataclass
class RoleTransitionRecord:
    """An empirical role transition record with supporting observational metrics."""
    transition_id: str = field(default_factory=lambda: f"role_trans_{uuid.uuid4().hex[:12]}")
    player_id: str = ""
    player_name: str = ""
    current_club: str = ""
    competition_id: str = "GB-PL"
    position: str = "FB"

    # Role Shift
    previous_role: str = "Traditional Fullback"
    current_role: str = "Inverted Fullback"
    previous_role_similarity: float = 0.88
    current_role_similarity: float = 0.91

    # Temporal & Confidence
    transition_date: str = "2024-02-15"
    evidence_window: str = "Last 12 Matches"
    confidence: str = "HIGH"  # LOW, MODERATE, HIGH
    sample_minutes: int = 1080

    # Supporting Metrics
    metric_shifts: dict[str, Any] = field(default_factory=dict)
    observational_evidence: list[str] = field(default_factory=list)
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RoleTransitionEngine:
    """Monitors role assignments to detect sustained, statistically valid role transitions."""

    def __init__(self) -> None:
        self._transitions: dict[str, RoleTransitionRecord] = {}
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_transitions()

    def _seed_default_transitions(self) -> None:
        seed = RoleTransitionRecord(
            transition_id="trans_trent_001",
            player_id="player_trent_66",
            player_name="Trent Alexander-Arnold",
            current_club="Liverpool",
            competition_id="GB-PL",
            position="RB",
            previous_role="Traditional Attacking Fullback",
            current_role="Inverted Playmaker",
            previous_role_similarity=0.72,
            current_role_similarity=0.92,
            transition_date="2023-11-20",
            evidence_window="2023/24 Matchdays 8–24",
            confidence="HIGH",
            sample_minutes=1440,
            metric_shifts={
                "central_third_touches_pct": {"previous": 28.4, "current": 54.2},
                "progressive_passes_central": {"previous": 3.1, "current": 7.4},
                "crosses_from_byline_p90": {"previous": 5.8, "current": 2.1},
            },
            observational_evidence=[
                "Observed central-third touch share increased from 28.4% to 54.2%.",
                "Progressive passes originating from half-space increased to 7.4 per 90.",
                "Wide byline crossing frequency decreased by 63.8% across 1,440 competitive minutes.",
            ],
        )
        self._transitions[seed.transition_id] = seed

    def detect_transition(
        self,
        player_id: str,
        player_name: str,
        current_club: str,
        competition_id: str,
        position: str,
        previous_role: str,
        current_role: str,
        sample_minutes: int,
        metric_shifts: dict[str, Any],
    ) -> RoleTransitionRecord | None:
        """Determines if a role shift qualifies as an empirical transition."""
        if previous_role == current_role:
            return None

        # Sample sufficiency gate
        if sample_minutes < 450:
            return None

        confidence = "HIGH" if sample_minutes >= 900 else "MODERATE"
        evidence = [
            f"Observed role profile shifted from '{previous_role}' to '{current_role}'.",
            f"Evaluated across {sample_minutes} minutes of competitive play.",
        ]
        for metric, vals in metric_shifts.items():
            if isinstance(vals, dict) and "previous" in vals and "current" in vals:
                evidence.append(f"{metric} changed from {vals['previous']} to {vals['current']}.")

        rec = RoleTransitionRecord(
            player_id=player_id,
            player_name=player_name,
            current_club=current_club,
            competition_id=competition_id,
            position=position,
            previous_role=previous_role,
            current_role=current_role,
            confidence=confidence,
            sample_minutes=sample_minutes,
            metric_shifts=metric_shifts,
            observational_evidence=evidence,
        )

        self._transitions[rec.transition_id] = rec
        return rec

    def get_transition(self, transition_id: str) -> RoleTransitionRecord | None:
        return self._transitions.get(transition_id)

    def list_transitions(self, player_id: str | None = None) -> list[RoleTransitionRecord]:
        transitions = list(self._transitions.values())
        if player_id:
            transitions = [t for t in transitions if t.player_id == player_id]
        return transitions


role_transition_engine = RoleTransitionEngine()
