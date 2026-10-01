"""Evidence-Gated Role Transition Research for Phase 15.

Studies transitions:
- CB -> FB
- FB -> CB
- DM -> CM
- CM -> AM
- Winger -> Forward
- Forward -> Wide Forward

Rules:
- Requires minimum appearances (>= 5) and minimum minutes (>= 450) in new role.
- Never infers role transition from a single match.
- Classifies: ROLE_TRANSITION_CONFIRMED, ROLE_TRANSITION_POSSIBLE, INSUFFICIENT_DATA.
"""

from typing import Any
from pydantic import BaseModel, Field
from app.phase15 import RoleTransitionStatus
from app.dev_fixtures import dev_seed_enabled


class RoleTransitionEvaluation(BaseModel):
    player_id: str
    source_role: str
    target_role: str
    target_role_minutes: int
    target_role_appearances: int
    competition: str
    temporal_span: dict[str, str]
    status: RoleTransitionStatus
    adaptation_indicators: dict[str, float] = Field(default_factory=dict)
    rationale: list[str] = Field(default_factory=list)


class RoleTransitionResearchEngine:
    """Evaluates role transitions under strict empirical sample gates."""

    def __init__(self, min_minutes: int = 450, min_appearances: int = 5) -> None:
        self.min_minutes = min_minutes
        self.min_appearances = min_appearances
        self._transitions: dict[str, RoleTransitionEvaluation] = {}

    def evaluate_transition(
        self,
        player_id: str,
        source_role: str,
        target_role: str,
        target_role_minutes: int,
        target_role_appearances: int,
        competition: str,
        temporal_span: dict[str, str],
        adaptation_indicators: dict[str, float] | None = None,
    ) -> RoleTransitionEvaluation:
        rationale: list[str] = []

        if target_role_appearances <= 1:
            status = RoleTransitionStatus.INSUFFICIENT_DATA
            rationale.append("Single-match appearance is insufficient to infer a systematic role transition.")
        elif target_role_appearances < self.min_appearances or target_role_minutes < self.min_minutes:
            status = RoleTransitionStatus.ROLE_TRANSITION_POSSIBLE
            rationale.append(
                f"Emerging role usage: {target_role_appearances} apps, {target_role_minutes} mins (threshold: {self.min_appearances} apps, {self.min_minutes} mins)."
            )
        else:
            status = RoleTransitionStatus.ROLE_TRANSITION_CONFIRMED
            rationale.append(
                f"Sustained role transition confirmed: {target_role_appearances} apps across {target_role_minutes} mins in {competition}."
            )

        evaluation = RoleTransitionEvaluation(
            player_id=player_id,
            source_role=source_role,
            target_role=target_role,
            target_role_minutes=target_role_minutes,
            target_role_appearances=target_role_appearances,
            competition=competition,
            temporal_span=temporal_span,
            status=status,
            adaptation_indicators=adaptation_indicators or {},
            rationale=rationale,
        )

        self._transitions[f"{player_id}:{source_role}->{target_role}"] = evaluation
        return evaluation

    def get_transition(self, player_id: str, source_role: str, target_role: str) -> RoleTransitionEvaluation:
        key = f"{player_id}:{source_role}->{target_role}"
        if key not in self._transitions:
            raise KeyError(f"Transition evaluation '{key}' not found.")
        return self._transitions[key]

    def list_transitions(self, status: RoleTransitionStatus | None = None) -> list[RoleTransitionEvaluation]:
        transitions = list(self._transitions.values())
        if status:
            transitions = [t for t in transitions if t.status == status]
        return transitions


_GLOBAL_ROLE_TRANSITION_ENGINE: RoleTransitionResearchEngine | None = None


def get_role_transition_engine() -> RoleTransitionResearchEngine:
    global _GLOBAL_ROLE_TRANSITION_ENGINE
    if _GLOBAL_ROLE_TRANSITION_ENGINE is None:
        _GLOBAL_ROLE_TRANSITION_ENGINE = RoleTransitionResearchEngine()
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            # Seed confirmed transition: FB -> Inverted CM / Wide CB
            _GLOBAL_ROLE_TRANSITION_ENGINE.evaluate_transition(
                player_id="ply_john_stones",
                source_role="Centre-Back",
                target_role="Inverted Defensive Midfielder",
                target_role_minutes=1120,
                target_role_appearances=14,
                competition="EPL",
                temporal_span={"start": "2023-01-01", "end": "2024-05-30"},
                adaptation_indicators={"retention_under_pressure": 0.91, "progression_rate": 0.84},
            )
            # Seed emerging transition: Winger -> Central Forward
            _GLOBAL_ROLE_TRANSITION_ENGINE.evaluate_transition(
                player_id="ply_emerging_winger",
                source_role="Right Winger",
                target_role="Central Striker",
                target_role_minutes=260,
                target_role_appearances=3,
                competition="La_Liga",
                temporal_span={"start": "2024-01-15", "end": "2024-03-30"},
                adaptation_indicators={"box_touches_p90": 5.8},
            )
    return _GLOBAL_ROLE_TRANSITION_ENGINE
