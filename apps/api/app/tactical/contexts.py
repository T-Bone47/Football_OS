"""Tactical Contexts and Requirement Models (Phase 2 Slice 3).
Defines standard tactical systems, formations, positions, and dimensional requirements
reusing the verified Role Discovery vocabulary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.roles.registry import (
    CONTROLLED_ARCHETYPES,
    DIMENSIONS,
    PositionGroup,
    map_position_to_group,
)

TACTICAL_CONTEXT_VERSION = "tactical_context_v1"


@dataclass(frozen=True)
class TacticalRequirement:
    """Requirement for a single functional dimension within a tactical context."""
    dimension: str  # one of the 9 canonical dimensions
    required_strength: float  # [0.0, 1.0]
    importance_weight: float  # [0.0, 1.0], relative importance
    minimum_threshold: float | None = None  # critical minimum required score
    preferred_range: tuple[float, float] | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TacticalContext:
    """Canonical representation of a tactical setup, formation, role, and requirements."""
    context_id: str
    formation: str  # e.g. '4-3-3', '4-2-3-1', '4-4-2', '3-5-2', '3-4-3'
    target_position: str  # e.g. 'DM', 'CM', 'RW', 'ST', 'CB', 'GK'
    position_group: PositionGroup
    target_role: str  # Controlled archetype name
    requirements: list[TacticalRequirement] = field(default_factory=list)
    possession_style: str | None = None  # e.g. 'HIGH_POSSESSION', 'DIRECT', 'COUNTER_ATTACK'
    pressing_style: str | None = None  # e.g. 'HIGH_PRESS', 'MID_BLOCK', 'LOW_BLOCK'
    build_up_style: str | None = None  # e.g. 'SHORT_PASSING', 'LONG_BALL'
    transition_style: str | None = None
    version: str = TACTICAL_CONTEXT_VERSION
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "formation": self.formation,
            "target_position": self.target_position,
            "position_group": self.position_group.value,
            "target_role": self.target_role,
            "requirements": [r.to_dict() for r in self.requirements],
            "possession_style": self.possession_style,
            "pressing_style": self.pressing_style,
            "build_up_style": self.build_up_style,
            "transition_style": self.transition_style,
            "version": self.version,
            "description": self.description,
        }


# Standard Catalog of Pre-configured Tactical Contexts
STANDARD_TACTICAL_CONTEXTS: dict[str, TacticalContext] = {
    # Midfield Contexts
    "433_dm_deep_distributor": TacticalContext(
        context_id="433_dm_deep_distributor",
        formation="4-3-3",
        target_position="DM",
        position_group=PositionGroup.MID,
        target_role="Deep Distributor",
        possession_style="HIGH_POSSESSION",
        build_up_style="SHORT_PASSING",
        description="Deep pivot in a 4-3-3 controlling tempo, receiving from center-backs, and initiating progressive attacks.",
        requirements=[
            TacticalRequirement("distribution", required_strength=0.80, importance_weight=0.35, minimum_threshold=0.55),
            TacticalRequirement("progression", required_strength=0.70, importance_weight=0.25, minimum_threshold=0.45),
            TacticalRequirement("defending", required_strength=0.60, importance_weight=0.20, minimum_threshold=0.40),
            TacticalRequirement("duels", required_strength=0.55, importance_weight=0.10),
            TacticalRequirement("carrying", required_strength=0.50, importance_weight=0.10),
        ],
    ),
    "433_dm_ball_winner": TacticalContext(
        context_id="433_dm_ball_winner",
        formation="4-3-3",
        target_position="DM",
        position_group=PositionGroup.MID,
        target_role="Ball-Winning Midfielder",
        pressing_style="HIGH_PRESS",
        description="Aggressive defensive anchor intercepting transitions and winning ground/aerial contests.",
        requirements=[
            TacticalRequirement("defending", required_strength=0.85, importance_weight=0.40, minimum_threshold=0.60),
            TacticalRequirement("duels", required_strength=0.80, importance_weight=0.30, minimum_threshold=0.55),
            TacticalRequirement("distribution", required_strength=0.60, importance_weight=0.20),
            TacticalRequirement("discipline", required_strength=0.60, importance_weight=0.10),
        ],
    ),
    "4231_cm_box_to_box": TacticalContext(
        context_id="4231_cm_box_to_box",
        formation="4-2-3-1",
        target_position="CM",
        position_group=PositionGroup.MID,
        target_role="Box-to-Box Midfielder",
        description="High-stamina double pivot midfielder active in both defensive phases and second-line attacking runs.",
        requirements=[
            TacticalRequirement("progression", required_strength=0.75, importance_weight=0.25, minimum_threshold=0.50),
            TacticalRequirement("defending", required_strength=0.70, importance_weight=0.25, minimum_threshold=0.45),
            TacticalRequirement("duels", required_strength=0.65, importance_weight=0.20),
            TacticalRequirement("distribution", required_strength=0.70, importance_weight=0.15),
            TacticalRequirement("finishing", required_strength=0.50, importance_weight=0.15),
        ],
    ),
    "4231_am_chance_creator": TacticalContext(
        context_id="4231_am_chance_creator",
        formation="4-2-3-1",
        target_position="AM",
        position_group=PositionGroup.MID,
        target_role="Chance Creator",
        description="Central creative hub threading through balls, creating shot actions, and unlocking low blocks.",
        requirements=[
            TacticalRequirement("creation", required_strength=0.85, importance_weight=0.40, minimum_threshold=0.60),
            TacticalRequirement("progression", required_strength=0.75, importance_weight=0.25, minimum_threshold=0.50),
            TacticalRequirement("carrying", required_strength=0.70, importance_weight=0.20),
            TacticalRequirement("finishing", required_strength=0.55, importance_weight=0.15),
        ],
    ),
    "433_cm_progressive_midfielder": TacticalContext(
        context_id="433_cm_progressive_midfielder",
        formation="4-3-3",
        target_position="CM",
        position_group=PositionGroup.MID,
        target_role="Progressive Midfielder",
        description="Vertical 8 carrying and passing between lines to break opponent defensive blocks.",
        requirements=[
            TacticalRequirement("progression", required_strength=0.85, importance_weight=0.40, minimum_threshold=0.60),
            TacticalRequirement("distribution", required_strength=0.75, importance_weight=0.30),
            TacticalRequirement("carrying", required_strength=0.70, importance_weight=0.20),
            TacticalRequirement("creation", required_strength=0.60, importance_weight=0.10),
        ],
    ),

    # Defender Contexts
    "433_cb_ball_player": TacticalContext(
        context_id="433_cb_ball_player",
        formation="4-3-3",
        target_position="CB",
        position_group=PositionGroup.DEF,
        target_role="Ball-Playing Defender",
        possession_style="HIGH_POSSESSION",
        description="Central defender initiating build-up sequences with long diagonal and line-breaking passes.",
        requirements=[
            TacticalRequirement("defending", required_strength=0.80, importance_weight=0.35, minimum_threshold=0.55),
            TacticalRequirement("distribution", required_strength=0.75, importance_weight=0.35, minimum_threshold=0.50),
            TacticalRequirement("duels", required_strength=0.70, importance_weight=0.15),
            TacticalRequirement("progression", required_strength=0.65, importance_weight=0.15),
        ],
    ),
    "442_cb_stopper": TacticalContext(
        context_id="442_cb_stopper",
        formation="4-4-2",
        target_position="CB",
        position_group=PositionGroup.DEF,
        target_role="Stopper",
        description="Dominant defensive center-back commanding aerial duels, clearances, and physical protection.",
        requirements=[
            TacticalRequirement("defending", required_strength=0.85, importance_weight=0.45, minimum_threshold=0.65),
            TacticalRequirement("duels", required_strength=0.85, importance_weight=0.35, minimum_threshold=0.60),
            TacticalRequirement("distribution", required_strength=0.50, importance_weight=0.15),
            TacticalRequirement("discipline", required_strength=0.60, importance_weight=0.05),
        ],
    ),
    "433_rb_progressive_fullback": TacticalContext(
        context_id="433_rb_progressive_fullback",
        formation="4-3-3",
        target_position="RB",
        position_group=PositionGroup.DEF,
        target_role="Progressive Fullback",
        description="High-energy wide defender providing width, dynamic carries, and flank delivery.",
        requirements=[
            TacticalRequirement("progression", required_strength=0.75, importance_weight=0.30, minimum_threshold=0.50),
            TacticalRequirement("carrying", required_strength=0.70, importance_weight=0.30),
            TacticalRequirement("defending", required_strength=0.65, importance_weight=0.25, minimum_threshold=0.40),
            TacticalRequirement("creation", required_strength=0.55, importance_weight=0.15),
        ],
    ),
    "442_lb_defensive_fullback": TacticalContext(
        context_id="442_lb_defensive_fullback",
        formation="4-4-2",
        target_position="LB",
        position_group=PositionGroup.DEF,
        target_role="Defensive Fullback",
        description="Positionally disciplined fullback providing 1v1 defensive containment and backline stability.",
        requirements=[
            TacticalRequirement("defending", required_strength=0.80, importance_weight=0.45, minimum_threshold=0.60),
            TacticalRequirement("duels", required_strength=0.75, importance_weight=0.35, minimum_threshold=0.50),
            TacticalRequirement("distribution", required_strength=0.55, importance_weight=0.20),
        ],
    ),
    "352_cb_inverted_fullback": TacticalContext(
        context_id="352_cb_inverted_fullback",
        formation="3-5-2",
        target_position="CB",
        position_group=PositionGroup.DEF,
        target_role="Inverted Fullback",
        description="Defender who steps into central midfield during possession phases to provide numerical superiority.",
        requirements=[
            TacticalRequirement("distribution", required_strength=0.75, importance_weight=0.35, minimum_threshold=0.50),
            TacticalRequirement("progression", required_strength=0.70, importance_weight=0.30, minimum_threshold=0.45),
            TacticalRequirement("defending", required_strength=0.70, importance_weight=0.20),
            TacticalRequirement("duels", required_strength=0.65, importance_weight=0.15),
        ],
    ),

    # Attacking Contexts
    "433_st_finisher": TacticalContext(
        context_id="433_st_finisher",
        formation="4-3-3",
        target_position="ST",
        position_group=PositionGroup.ATT,
        target_role="Finisher",
        description="Penalty-box penalty striker maximizing shot conversion and high goal threat.",
        requirements=[
            TacticalRequirement("finishing", required_strength=0.85, importance_weight=0.50, minimum_threshold=0.65),
            TacticalRequirement("creation", required_strength=0.55, importance_weight=0.20),
            TacticalRequirement("duels", required_strength=0.60, importance_weight=0.15),
            TacticalRequirement("carrying", required_strength=0.55, importance_weight=0.15),
        ],
    ),
    "433_lw_wide_creator": TacticalContext(
        context_id="433_lw_wide_creator",
        formation="4-3-3",
        target_position="LW",
        position_group=PositionGroup.ATT,
        target_role="Wide Creator",
        description="Winger specializing in 1v1 take-ons, isolating fullbacks, and servicing the central forward.",
        requirements=[
            TacticalRequirement("creation", required_strength=0.80, importance_weight=0.35, minimum_threshold=0.55),
            TacticalRequirement("carrying", required_strength=0.80, importance_weight=0.35, minimum_threshold=0.55),
            TacticalRequirement("progression", required_strength=0.70, importance_weight=0.20),
            TacticalRequirement("finishing", required_strength=0.50, importance_weight=0.10),
        ],
    ),
    "442_st_pressing_forward": TacticalContext(
        context_id="442_st_pressing_forward",
        formation="4-4-2",
        target_position="ST",
        position_group=PositionGroup.ATT,
        target_role="Pressing Forward",
        pressing_style="HIGH_PRESS",
        description="Hard-working forward initiating defensive triggers in the attacking third and contesting backlines.",
        requirements=[
            TacticalRequirement("defending", required_strength=0.70, importance_weight=0.35, minimum_threshold=0.45),
            TacticalRequirement("duels", required_strength=0.75, importance_weight=0.30, minimum_threshold=0.50),
            TacticalRequirement("finishing", required_strength=0.65, importance_weight=0.25),
            TacticalRequirement("progression", required_strength=0.55, importance_weight=0.10),
        ],
    ),
    "4231_st_target_forward": TacticalContext(
        context_id="4231_st_target_forward",
        formation="4-2-3-1",
        target_position="ST",
        position_group=PositionGroup.ATT,
        target_role="Target Forward",
        description="Physical reference point holding up play, winning aerial duals, and laying off to runners.",
        requirements=[
            TacticalRequirement("duels", required_strength=0.85, importance_weight=0.40, minimum_threshold=0.60),
            TacticalRequirement("finishing", required_strength=0.75, importance_weight=0.35, minimum_threshold=0.50),
            TacticalRequirement("distribution", required_strength=0.60, importance_weight=0.15),
            TacticalRequirement("creation", required_strength=0.50, importance_weight=0.10),
        ],
    ),
    "433_st_complete_forward": TacticalContext(
        context_id="433_st_complete_forward",
        formation="4-3-3",
        target_position="ST",
        position_group=PositionGroup.ATT,
        target_role="Complete Forward",
        description="All-around elite forward blending clinical finishing, link-up passing, and individual progression.",
        requirements=[
            TacticalRequirement("finishing", required_strength=0.80, importance_weight=0.35, minimum_threshold=0.60),
            TacticalRequirement("creation", required_strength=0.70, importance_weight=0.25),
            TacticalRequirement("carrying", required_strength=0.70, importance_weight=0.20),
            TacticalRequirement("progression", required_strength=0.65, importance_weight=0.10),
            TacticalRequirement("duels", required_strength=0.65, importance_weight=0.10),
        ],
    ),

    # Goalkeeper Contexts
    "433_gk_sweeper_keeper": TacticalContext(
        context_id="433_gk_sweeper_keeper",
        formation="4-3-3",
        target_position="GK",
        position_group=PositionGroup.GK,
        target_role="Sweeper Keeper",
        description="Proactive goalkeeper playing behind a high line, participating in build-up passing and box departures.",
        requirements=[
            TacticalRequirement("goalkeeping", required_strength=0.80, importance_weight=0.50, minimum_threshold=0.60),
            TacticalRequirement("distribution", required_strength=0.75, importance_weight=0.40, minimum_threshold=0.50),
            TacticalRequirement("progression", required_strength=0.50, importance_weight=0.10),
        ],
    ),
    "442_gk_shot_stopper": TacticalContext(
        context_id="442_gk_shot_stopper",
        formation="4-4-2",
        target_position="GK",
        position_group=PositionGroup.GK,
        target_role="Shot Stopper",
        description="Traditional goalkeeper focused on reflex saves, aerial claiming, and high-percentage shot stopping.",
        requirements=[
            TacticalRequirement("goalkeeping", required_strength=0.90, importance_weight=0.80, minimum_threshold=0.70),
            TacticalRequirement("distribution", required_strength=0.50, importance_weight=0.15),
            TacticalRequirement("discipline", required_strength=0.60, importance_weight=0.05),
        ],
    ),
}


def get_standard_context(context_id: str) -> TacticalContext | None:
    """Fetches a standard pre-configured tactical context by ID."""
    return STANDARD_TACTICAL_CONTEXTS.get(context_id)


def build_custom_context(
    formation: str,
    target_position: str,
    target_role: str,
    possession_style: str | None = None,
    pressing_style: str | None = None,
) -> TacticalContext:
    """Constructs an ad-hoc tactical context based on canonical position and controlled archetype weights."""
    pos_group = map_position_to_group(target_position)

    # Derive requirements from controlled archetype weights
    requirements: list[TacticalRequirement] = []
    archetypes = CONTROLLED_ARCHETYPES.get(pos_group, [])
    matched_arch = next((a for a in archetypes if a["name"].lower() == target_role.lower()), None)

    if matched_arch:
        raw_weights = matched_arch["weights"]
        total_w = sum(abs(v) for v in raw_weights.values())
        for dim, w in raw_weights.items():
            if w > 0:
                normalized_w = round(w / total_w, 4)
                # Assign baseline requirement strength proportional to archetype emphasis
                strength = min(0.90, max(0.60, 0.60 + normalized_w * 0.5))
                requirements.append(
                    TacticalRequirement(
                        dimension=dim,
                        required_strength=strength,
                        importance_weight=normalized_w,
                        minimum_threshold=max(0.40, strength - 0.25),
                    )
                )
    else:
        # Generic baseline requirements for the position group
        default_dims = {
            PositionGroup.MID: ["distribution", "progression", "defending"],
            PositionGroup.DEF: ["defending", "duels", "distribution"],
            PositionGroup.ATT: ["finishing", "creation", "carrying"],
            PositionGroup.GK: ["goalkeeping", "distribution"],
        }.get(pos_group, ["distribution"])
        for dim in default_dims:
            requirements.append(
                TacticalRequirement(dimension=dim, required_strength=0.70, importance_weight=round(1.0 / len(default_dims), 2))
            )

    norm_formation = formation.replace(" ", "")
    norm_pos = target_position.upper()
    norm_role = target_role.lower().replace(" ", "_")
    context_id = f"custom_{norm_formation}_{norm_pos}_{norm_role}"

    return TacticalContext(
        context_id=context_id,
        formation=formation,
        target_position=target_position,
        position_group=pos_group,
        target_role=matched_arch["name"] if matched_arch else target_role,
        requirements=requirements,
        possession_style=possession_style,
        pressing_style=pressing_style,
    )
