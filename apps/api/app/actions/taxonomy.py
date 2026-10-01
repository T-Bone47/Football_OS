"""Action Taxonomy and Controlled Vocabulary for Football Intelligence OS (Phase 3.1).
Defines standard action categories, subtypes, outcomes, and provider mappings.
"""
from __future__ import annotations

import enum


class ActionType(str, enum.Enum):
    PASSING = "PASSING"
    CREATION = "CREATION"
    SHOOTING = "SHOOTING"
    DEFENDING = "DEFENDING"
    DUEL = "DUEL"
    DRIBBLE = "DRIBBLE"
    DISCIPLINE = "DISCIPLINE"
    GOALKEEPING = "GOALKEEPING"
    SUBSTITUTION = "SUBSTITUTION"
    OTHER = "OTHER"


class ActionSubtype(str, enum.Enum):
    # Passing
    PASS = "PASS"
    PASS_COMPLETED = "PASS_COMPLETED"
    PASS_INCOMPLETE = "PASS_INCOMPLETE"
    KEY_PASS = "KEY_PASS"
    ASSIST = "ASSIST"

    # Shooting
    SHOT = "SHOT"
    SHOT_ON_TARGET = "SHOT_ON_TARGET"
    SHOT_OFF_TARGET = "SHOT_OFF_TARGET"
    GOAL = "GOAL"
    PENALTY_GOAL = "PENALTY_GOAL"
    PENALTY_MISSED = "PENALTY_MISSED"

    # Defending
    TACKLE = "TACKLE"
    INTERCEPTION = "INTERCEPTION"
    BLOCK = "BLOCK"
    CLEARANCE = "CLEARANCE"
    RECOVERY = "RECOVERY"

    # Duels
    DUEL_CONTESTED = "DUEL_CONTESTED"
    DUEL_WON = "DUEL_WON"
    DUEL_LOST = "DUEL_LOST"

    # Dribbling & Ball Retention
    DRIBBLE_ATTEMPT = "DRIBBLE_ATTEMPT"
    DRIBBLE_SUCCESS = "DRIBBLE_SUCCESS"
    DRIBBLE_PAST = "DRIBBLE_PAST"

    # Discipline & Infractions
    FOUL_COMMITTED = "FOUL_COMMITTED"
    FOUL_DRAWN = "FOUL_DRAWN"
    YELLOW_CARD = "YELLOW_CARD"
    RED_CARD = "RED_CARD"
    PENALTY_COMMITTED = "PENALTY_COMMITTED"
    PENALTY_WON = "PENALTY_WON"

    # Goalkeeping
    SAVE = "SAVE"
    GOAL_CONCEDED = "GOAL_CONCEDED"
    PENALTY_SAVED = "PENALTY_SAVED"

    # Matchflow
    SUBSTITUTION_ON = "SUBSTITUTION_ON"
    SUBSTITUTION_OFF = "SUBSTITUTION_OFF"
    VAR_DECISION = "VAR_DECISION"
    OTHER = "OTHER"


class ActionOutcome(str, enum.Enum):
    SUCCESS = "SUCCESS"
    UNSUCCESSFUL = "UNSUCCESSFUL"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"
