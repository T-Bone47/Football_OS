"""Pure deterministic normalization functions transforming raw provider events and stats
into canonical action representations (Phase 3.1B).
"""
from __future__ import annotations

import uuid
from typing import Any

from app.actions.models import CanonicalAction
from app.actions.taxonomy import ActionOutcome, ActionSubtype, ActionType
from app.db.models.canonical import MatchEvent, PlayerMatchStats


NORMALIZATION_VERSION = "1.0"


def normalize_match_event(event: MatchEvent) -> list[CanonicalAction]:
    """Transforms a discrete MatchEvent timeline record into canonical actions.
    Preserves exact event minute, participants, and outcome without coordinate fabrication.
    """
    if not event.player_id or not event.match_id or not event.club_id:
        return []

    actions: list[CanonicalAction] = []
    e_type = (event.event_type or "").upper()
    e_detail = (event.event_detail or "").lower()

    if e_type == "GOAL":
        is_penalty = "penalty" in e_detail
        is_own_goal = "own goal" in e_detail
        subtype = (
            ActionSubtype.PENALTY_GOAL
            if is_penalty
            else ActionSubtype.GOAL
        )
        actions.append(
            CanonicalAction(
                id=uuid.uuid4(),
                match_id=event.match_id,
                player_id=event.player_id,
                club_id=event.club_id,
                period=None,
                minute=event.minute,
                extra_minute=event.extra_minute,
                action_type=ActionType.SHOOTING.value,
                action_subtype=subtype.value,
                action_quantity=1,
                outcome=ActionOutcome.SUCCESS.value if not is_own_goal else ActionOutcome.UNSUCCESSFUL.value,
                x=None,
                y=None,
                end_x=None,
                end_y=None,
                recipient_player_id=None,
                related_player_id=event.assist_player_id,
                provider="api-football",
                provider_event_id=event.provider_event_id,
                source_snapshot_id=event.snapshot_id,
                normalization_version=NORMALIZATION_VERSION,
                raw_data={"detail": event.event_detail, "comments": event.comments},
            )
        )
        if event.assist_player_id:
            actions.append(
                CanonicalAction(
                    id=uuid.uuid4(),
                    match_id=event.match_id,
                    player_id=event.assist_player_id,
                    club_id=event.club_id,
                    period=None,
                    minute=event.minute,
                    extra_minute=event.extra_minute,
                    action_type=ActionType.CREATION.value,
                    action_subtype=ActionSubtype.ASSIST.value,
                    action_quantity=1,
                    outcome=ActionOutcome.SUCCESS.value,
                    x=None,
                    y=None,
                    end_x=None,
                    end_y=None,
                    recipient_player_id=event.player_id,
                    related_player_id=None,
                    provider="api-football",
                    provider_event_id=event.provider_event_id,
                    source_snapshot_id=event.snapshot_id,
                    normalization_version=NORMALIZATION_VERSION,
                    raw_data={"detail": "Goal Assist"},
                )
            )

    elif e_type == "CARD":
        is_red = "red" in e_detail
        actions.append(
            CanonicalAction(
                id=uuid.uuid4(),
                match_id=event.match_id,
                player_id=event.player_id,
                club_id=event.club_id,
                period=None,
                minute=event.minute,
                extra_minute=event.extra_minute,
                action_type=ActionType.DISCIPLINE.value,
                action_subtype=ActionSubtype.RED_CARD.value if is_red else ActionSubtype.YELLOW_CARD.value,
                action_quantity=1,
                outcome=ActionOutcome.NEUTRAL.value,
                x=None,
                y=None,
                end_x=None,
                end_y=None,
                recipient_player_id=None,
                related_player_id=None,
                provider="api-football",
                provider_event_id=event.provider_event_id,
                source_snapshot_id=event.snapshot_id,
                normalization_version=NORMALIZATION_VERSION,
                raw_data={"comments": event.comments, "detail": event.event_detail},
            )
        )

    elif e_type == "SUBSTITUTION":
        actions.append(
            CanonicalAction(
                id=uuid.uuid4(),
                match_id=event.match_id,
                player_id=event.player_id,
                club_id=event.club_id,
                period=None,
                minute=event.minute,
                extra_minute=event.extra_minute,
                action_type=ActionType.SUBSTITUTION.value,
                action_subtype=ActionSubtype.SUBSTITUTION_OFF.value,
                action_quantity=1,
                outcome=ActionOutcome.NEUTRAL.value,
                x=None,
                y=None,
                end_x=None,
                end_y=None,
                recipient_player_id=event.assist_player_id,
                related_player_id=None,
                provider="api-football",
                provider_event_id=event.provider_event_id,
                source_snapshot_id=event.snapshot_id,
                normalization_version=NORMALIZATION_VERSION,
                raw_data={"detail": event.event_detail},
            )
        )
        if event.assist_player_id:
            actions.append(
                CanonicalAction(
                    id=uuid.uuid4(),
                    match_id=event.match_id,
                    player_id=event.assist_player_id,
                    club_id=event.club_id,
                    period=None,
                    minute=event.minute,
                    extra_minute=event.extra_minute,
                    action_type=ActionType.SUBSTITUTION.value,
                    action_subtype=ActionSubtype.SUBSTITUTION_ON.value,
                    action_quantity=1,
                    outcome=ActionOutcome.NEUTRAL.value,
                    x=None,
                    y=None,
                    end_x=None,
                    end_y=None,
                    recipient_player_id=None,
                    related_player_id=event.player_id,
                    provider="api-football",
                    provider_event_id=event.provider_event_id,
                    source_snapshot_id=event.snapshot_id,
                    normalization_version=NORMALIZATION_VERSION,
                    raw_data={"detail": event.event_detail},
                )
            )

    return actions


def normalize_player_match_stats(stats: PlayerMatchStats) -> list[CanonicalAction]:
    """Transforms fixture-level PlayerMatchStats tallies into canonical actions.
    Preserves exact quantities, outcomes, and raw values.
    """
    if not stats.player_id or not stats.match_id or not stats.club_id:
        return []

    actions: list[CanonicalAction] = []
    base_minute = 90  # Aggregate match actions assign to end of match

    def add_action(
        a_type: ActionType,
        subtype: ActionSubtype,
        qty: int,
        outcome: ActionOutcome,
        raw_key: str,
    ) -> None:
        if qty > 0:
            actions.append(
                CanonicalAction(
                    id=uuid.uuid4(),
                    match_id=stats.match_id,
                    player_id=stats.player_id,
                    club_id=stats.club_id,
                    period=None,
                    minute=base_minute,
                    extra_minute=None,
                    action_type=a_type.value,
                    action_subtype=subtype.value,
                    action_quantity=qty,
                    outcome=outcome.value,
                    x=None,
                    y=None,
                    end_x=None,
                    end_y=None,
                    recipient_player_id=None,
                    related_player_id=None,
                    provider="api-football",
                    provider_event_id=None,
                    source_snapshot_id=stats.snapshot_id,
                    normalization_version=NORMALIZATION_VERSION,
                    raw_data={"metric": raw_key, "value": qty},
                )
            )

    # 1. Passing
    if stats.passes_total and stats.passes_total > 0:
        acc_pct = stats.pass_accuracy or 0.0
        completed = int(round(stats.passes_total * (acc_pct / 100.0)))
        incomplete = max(0, stats.passes_total - completed)
        add_action(ActionType.PASSING, ActionSubtype.PASS_COMPLETED, completed, ActionOutcome.SUCCESS, "passes_completed")
        add_action(ActionType.PASSING, ActionSubtype.PASS_INCOMPLETE, incomplete, ActionOutcome.UNSUCCESSFUL, "passes_incomplete")

    # 2. Key Passes
    if stats.passes_key and stats.passes_key > 0:
        add_action(ActionType.CREATION, ActionSubtype.KEY_PASS, stats.passes_key, ActionOutcome.SUCCESS, "passes_key")

    # 3. Shooting
    if stats.shots_total and stats.shots_total > 0:
        on_target = stats.shots_on_target or 0
        off_target = max(0, stats.shots_total - on_target)
        add_action(ActionType.SHOOTING, ActionSubtype.SHOT_ON_TARGET, on_target, ActionOutcome.SUCCESS, "shots_on_target")
        add_action(ActionType.SHOOTING, ActionSubtype.SHOT_OFF_TARGET, off_target, ActionOutcome.UNSUCCESSFUL, "shots_off_target")

    # 4. Defending
    if stats.tackles_total and stats.tackles_total > 0:
        add_action(ActionType.DEFENDING, ActionSubtype.TACKLE, stats.tackles_total, ActionOutcome.SUCCESS, "tackles_total")
    if stats.interceptions and stats.interceptions > 0:
        add_action(ActionType.DEFENDING, ActionSubtype.INTERCEPTION, stats.interceptions, ActionOutcome.SUCCESS, "interceptions")
    if stats.blocks and stats.blocks > 0:
        add_action(ActionType.DEFENDING, ActionSubtype.BLOCK, stats.blocks, ActionOutcome.SUCCESS, "blocks")

    # 5. Duels
    if stats.duels_total and stats.duels_total > 0:
        won = stats.duels_won or 0
        lost = max(0, stats.duels_total - won)
        add_action(ActionType.DUEL, ActionSubtype.DUEL_WON, won, ActionOutcome.SUCCESS, "duels_won")
        add_action(ActionType.DUEL, ActionSubtype.DUEL_LOST, lost, ActionOutcome.UNSUCCESSFUL, "duels_lost")

    # 6. Dribbles
    if stats.dribbles_success and stats.dribbles_success > 0:
        add_action(ActionType.DRIBBLE, ActionSubtype.DRIBBLE_SUCCESS, stats.dribbles_success, ActionOutcome.SUCCESS, "dribbles_success")

    # 7. Fouls
    if stats.fouls_committed and stats.fouls_committed > 0:
        add_action(ActionType.DISCIPLINE, ActionSubtype.FOUL_COMMITTED, stats.fouls_committed, ActionOutcome.NEUTRAL, "fouls_committed")
    if stats.fouls_drawn and stats.fouls_drawn > 0:
        add_action(ActionType.DISCIPLINE, ActionSubtype.FOUL_DRAWN, stats.fouls_drawn, ActionOutcome.SUCCESS, "fouls_drawn")

    # 8. Goalkeeping
    if stats.position == "G":
        if stats.saves and stats.saves > 0:
            add_action(ActionType.GOALKEEPING, ActionSubtype.SAVE, stats.saves, ActionOutcome.SUCCESS, "saves")
        if stats.goals_conceded and stats.goals_conceded > 0:
            add_action(ActionType.GOALKEEPING, ActionSubtype.GOAL_CONCEDED, stats.goals_conceded, ActionOutcome.UNSUCCESSFUL, "goals_conceded")

    return actions
