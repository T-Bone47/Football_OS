"""Role Feature Registry and Definitions (Phase 2 Slice 2).
Provides typed, versioned metadata for selected role features, position groups,
and the controlled archetype vocabulary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class PositionGroup(str, Enum):
    GK = "GK"
    DEF = "DEF"
    MID = "MID"
    ATT = "ATT"


def map_position_to_group(pos: str | None) -> PositionGroup:
    """Maps nominal provider/canonical position codes to broad position families."""
    if not pos:
        return PositionGroup.MID
    normalized = pos.strip().upper()
    if normalized in {"G", "GK", "GOALKEEPER"}:
        return PositionGroup.GK
    if normalized in {"D", "DF", "CB", "LB", "RB", "WB", "LWB", "RWB", "DEFENDER"}:
        return PositionGroup.DEF
    if normalized in {"M", "MF", "CM", "DM", "AM", "LM", "RM", "MIDFIELDER"}:
        return PositionGroup.MID
    if normalized in {"F", "FW", "ST", "CF", "LW", "RW", "W", "ATTACKER", "FORWARD"}:
        return PositionGroup.ATT
    return PositionGroup.MID


@dataclass(frozen=True)
class RoleFeatureDefinition:
    name: str
    dimension: str  # distribution, progression, creation, finishing, defending, duels, carrying, discipline, goalkeeping
    source_feature: str  # feature name from FeatureSnapshot
    direction: str  # 'positive' (higher is better for role), 'neutral', 'negative'
    position_groups: list[PositionGroup]
    default_value: float
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "position_groups": [p.value for p in self.position_groups],
        }


ROLE_FEATURE_SET_VERSION = "role_feature_set_v1"

# Dimension definitions: 9 functional dimensions
DIMENSIONS = [
    "distribution",
    "progression",
    "creation",
    "finishing",
    "defending",
    "duels",
    "carrying",
    "discipline",
    "goalkeeping",
]

# Controlled Vocabulary for Role Archetypes by Position Group
CONTROLLED_ARCHETYPES: dict[PositionGroup, list[dict[str, Any]]] = {
    PositionGroup.MID: [
        {
            "name": "Deep Distributor",
            "description": "Orchestrates build-up from deep, high volume and passing accuracy, lower forward creation.",
            "weights": {"distribution": 0.45, "progression": 0.25, "defending": 0.15, "creation": 0.10, "carrying": 0.05},
        },
        {
            "name": "Progressive Midfielder",
            "description": "Drives play forward through vertical passing and ball advancement.",
            "weights": {"progression": 0.40, "distribution": 0.30, "carrying": 0.20, "creation": 0.10},
        },
        {
            "name": "Ball-Winning Midfielder",
            "description": "High defensive engagement, disruptive tackles, interceptions, and duel volume.",
            "weights": {"defending": 0.45, "duels": 0.35, "discipline": -0.10, "distribution": 0.10},
        },
        {
            "name": "Chance Creator",
            "description": "High key pass volume, shot-creation, and penalty-box service.",
            "weights": {"creation": 0.45, "progression": 0.25, "carrying": 0.15, "finishing": 0.15},
        },
        {
            "name": "Box-to-Box Midfielder",
            "description": "Dynamic two-way midfielder active in both defensive actions and progression/finishing.",
            "weights": {"defending": 0.25, "progression": 0.25, "duels": 0.20, "distribution": 0.15, "finishing": 0.15},
        },
    ],
    PositionGroup.DEF: [
        {
            "name": "Ball-Playing Defender",
            "description": "Comfortable stepping out with passes and initiating attacking sequences from deep.",
            "weights": {"distribution": 0.40, "defending": 0.35, "progression": 0.15, "duels": 0.10},
        },
        {
            "name": "Stopper",
            "description": "Traditional central defender focused on aerial duels, clearances, tackles, and box protection.",
            "weights": {"defending": 0.50, "duels": 0.35, "discipline": -0.05, "distribution": 0.10},
        },
        {
            "name": "Progressive Fullback",
            "description": "Wide defender who advances up the flank, contributing carries, progression, and crosses.",
            "weights": {"progression": 0.35, "carrying": 0.30, "defending": 0.20, "creation": 0.15},
        },
        {
            "name": "Defensive Fullback",
            "description": "Focuses on wide 1v1 containment, positional security, and defensive duel suppression.",
            "weights": {"defending": 0.50, "duels": 0.30, "distribution": 0.15, "progression": 0.05},
        },
        {
            "name": "Inverted Fullback",
            "description": "Tucks into midfield areas during possession to aid central circulation and progression.",
            "weights": {"distribution": 0.40, "progression": 0.30, "defending": 0.20, "duels": 0.10},
        },
    ],
    PositionGroup.ATT: [
        {
            "name": "Finisher",
            "description": "Primary goal threat, high shot volume, conversion, and penalty-box occupation.",
            "weights": {"finishing": 0.55, "creation": 0.20, "duels": 0.15, "carrying": 0.10},
        },
        {
            "name": "Wide Creator",
            "description": "Operates in wide areas to beat defenders via dribbles, providing crosses and key passes.",
            "weights": {"creation": 0.35, "carrying": 0.35, "progression": 0.20, "finishing": 0.10},
        },
        {
            "name": "Pressing Forward",
            "description": "Harries backlines, high defensive actions in the final third, and contest-heavy duels.",
            "weights": {"defending": 0.35, "duels": 0.30, "finishing": 0.25, "progression": 0.10},
        },
        {
            "name": "Target Forward",
            "description": "Physical focal point competing in aerial/ground duels to hold up play and finish inside the box.",
            "weights": {"duels": 0.40, "finishing": 0.35, "distribution": 0.15, "creation": 0.10},
        },
        {
            "name": "Complete Forward",
            "description": "Multi-faceted attacker contributing high finishing, creative passing, and dynamic carries.",
            "weights": {"finishing": 0.35, "creation": 0.25, "carrying": 0.20, "progression": 0.10, "duels": 0.10},
        },
    ],
    PositionGroup.GK: [
        {
            "name": "Sweeper Keeper",
            "description": "Modern goalkeeper who actively participates in possession build-up and proactive sweeping.",
            "weights": {"goalkeeping": 0.50, "distribution": 0.40, "progression": 0.10},
        },
        {
            "name": "Shot Stopper",
            "description": "Traditional line goalkeeper with elite reflex saving and goal prevention focus.",
            "weights": {"goalkeeping": 0.80, "distribution": 0.15, "discipline": 0.05},
        },
    ],
}


# Selected Role Features Registry
ROLE_FEATURE_REGISTRY: dict[str, RoleFeatureDefinition] = {
    # Dimension A: Distribution
    "passes_per_90": RoleFeatureDefinition(
        name="passes_per_90",
        dimension="distribution",
        source_feature="passes_per_90_last_5",
        direction="positive",
        position_groups=[PositionGroup.GK, PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Passes attempted per 90 minutes in last 5 matches",
    ),
    "pass_accuracy": RoleFeatureDefinition(
        name="pass_accuracy",
        dimension="distribution",
        source_feature="pass_accuracy_avg_last_5",
        direction="positive",
        position_groups=[PositionGroup.GK, PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=75.0,
        description="Average passing accuracy percentage in last 5 matches",
    ),
    "passes_total": RoleFeatureDefinition(
        name="passes_total",
        dimension="distribution",
        source_feature="passes_total_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID],
        default_value=0.0,
        description="Total passes in window",
    ),

    # Dimension B: Progression
    "key_passes_per_90": RoleFeatureDefinition(
        name="key_passes_per_90",
        dimension="progression",
        source_feature="passes_key_per_90_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Key passes creating shooting chances per 90 minutes",
    ),
    "key_passes_total": RoleFeatureDefinition(
        name="key_passes_total",
        dimension="progression",
        source_feature="passes_key_last_5",
        direction="positive",
        position_groups=[PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Total key passes in window",
    ),
    "progressive_dribbles": RoleFeatureDefinition(
        name="progressive_dribbles",
        dimension="progression",
        source_feature="dribbles_success_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Successful dribbles advancing the ball",
    ),

    # Dimension C: Creation
    "assists_per_90": RoleFeatureDefinition(
        name="assists_per_90",
        dimension="creation",
        source_feature="assists_per_90_last_5",
        direction="positive",
        position_groups=[PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Goal assists delivered per 90 minutes",
    ),
    "assists_total": RoleFeatureDefinition(
        name="assists_total",
        dimension="creation",
        source_feature="assists_last_5",
        direction="positive",
        position_groups=[PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Total assists in window",
    ),
    "shots_on_target_per_90": RoleFeatureDefinition(
        name="shots_on_target_per_90",
        dimension="creation",
        source_feature="shots_on_target_per_90_last_5",
        direction="positive",
        position_groups=[PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Shots on target per 90 minutes",
    ),

    # Dimension D: Finishing
    "goals_per_90": RoleFeatureDefinition(
        name="goals_per_90",
        dimension="finishing",
        source_feature="goals_per_90_last_5",
        direction="positive",
        position_groups=[PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Goals scored per 90 minutes",
    ),
    "goals_total": RoleFeatureDefinition(
        name="goals_total",
        dimension="finishing",
        source_feature="goals_last_5",
        direction="positive",
        position_groups=[PositionGroup.ATT],
        default_value=0.0,
        description="Total goals in window",
    ),
    "shots_per_90": RoleFeatureDefinition(
        name="shots_per_90",
        dimension="finishing",
        source_feature="shots_per_90_last_5",
        direction="positive",
        position_groups=[PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Total shots attempted per 90 minutes",
    ),
    "shots_total": RoleFeatureDefinition(
        name="shots_total",
        dimension="finishing",
        source_feature="shots_total_last_5",
        direction="positive",
        position_groups=[PositionGroup.ATT],
        default_value=0.0,
        description="Total shots attempted in window",
    ),

    # Dimension E: Defending
    "tackles_per_90": RoleFeatureDefinition(
        name="tackles_per_90",
        dimension="defending",
        source_feature="tackles_per_90_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Tackles executed per 90 minutes",
    ),
    "tackles_total": RoleFeatureDefinition(
        name="tackles_total",
        dimension="defending",
        source_feature="tackles_total_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID],
        default_value=0.0,
        description="Total tackles in window",
    ),
    "interceptions": RoleFeatureDefinition(
        name="interceptions",
        dimension="defending",
        source_feature="interceptions_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID],
        default_value=0.0,
        description="Passes intercepted in window",
    ),
    "blocks": RoleFeatureDefinition(
        name="blocks",
        dimension="defending",
        source_feature="blocks_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID],
        default_value=0.0,
        description="Shots/passes blocked in window",
    ),
    "defensive_actions_per_90": RoleFeatureDefinition(
        name="defensive_actions_per_90",
        dimension="defending",
        source_feature="defensive_actions_per_90_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Combined defensive actions per 90 minutes",
    ),

    # Dimension F: Duels
    "duels_total": RoleFeatureDefinition(
        name="duels_total",
        dimension="duels",
        source_feature="duels_total_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Total ground/aerial duels contested in window",
    ),
    "duels_won": RoleFeatureDefinition(
        name="duels_won",
        dimension="duels",
        source_feature="duels_won_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Total duels won in window",
    ),
    "duel_win_rate": RoleFeatureDefinition(
        name="duel_win_rate",
        dimension="duels",
        source_feature="duel_win_rate_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.5,
        description="Duel win rate percentage in window",
    ),

    # Dimension G: Ball Carrying / Dribbling
    "dribbles_attempts": RoleFeatureDefinition(
        name="dribbles_attempts",
        dimension="carrying",
        source_feature="dribbles_attempts_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Total 1v1 dribbles attempted in window",
    ),
    "dribbles_success": RoleFeatureDefinition(
        name="dribbles_success",
        dimension="carrying",
        source_feature="dribbles_success_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Total successful dribbles in window",
    ),
    "dribble_success_rate": RoleFeatureDefinition(
        name="dribble_success_rate",
        dimension="carrying",
        source_feature="dribble_success_rate_last_5",
        direction="positive",
        position_groups=[PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.5,
        description="Percentage of dribbles completed successfully",
    ),

    # Dimension H: Discipline
    "fouls_committed": RoleFeatureDefinition(
        name="fouls_committed",
        dimension="discipline",
        source_feature="fouls_committed_last_5",
        direction="negative",
        position_groups=[PositionGroup.GK, PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Fouls committed in window",
    ),
    "yellow_cards": RoleFeatureDefinition(
        name="yellow_cards",
        dimension="discipline",
        source_feature="yellow_cards_last_5",
        direction="negative",
        position_groups=[PositionGroup.GK, PositionGroup.DEF, PositionGroup.MID, PositionGroup.ATT],
        default_value=0.0,
        description="Yellow cards accumulated in window",
    ),

    # Dimension I: Goalkeeping
    "saves": RoleFeatureDefinition(
        name="saves",
        dimension="goalkeeping",
        source_feature="saves_last_5",
        direction="positive",
        position_groups=[PositionGroup.GK],
        default_value=0.0,
        description="Saves made in window (goalkeepers only)",
    ),
    "goals_conceded": RoleFeatureDefinition(
        name="goals_conceded",
        dimension="goalkeeping",
        source_feature="goals_conceded_last_5",
        direction="negative",
        position_groups=[PositionGroup.GK],
        default_value=0.0,
        description="Goals conceded in window (goalkeepers only)",
    ),
    "clean_sheets": RoleFeatureDefinition(
        name="clean_sheets",
        dimension="goalkeeping",
        source_feature="clean_sheets_last_5",
        direction="positive",
        position_groups=[PositionGroup.GK],
        default_value=0.0,
        description="Matches with clean sheet preserved",
    ),
    "save_rate": RoleFeatureDefinition(
        name="save_rate",
        dimension="goalkeeping",
        source_feature="save_rate_last_5",
        direction="positive",
        position_groups=[PositionGroup.GK],
        default_value=0.7,
        description="Save percentage saves / (saves + goals_conceded)",
    ),
}
