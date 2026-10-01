"""Unit tests for Action Normalization, Taxonomy, and Transformation (Phase 3.1A/B/C)."""
import uuid
from app.actions.normalizer import normalize_match_event, normalize_player_match_stats
from app.actions.taxonomy import ActionOutcome, ActionSubtype, ActionType
from app.db.models.canonical import MatchEvent, PlayerMatchStats


def test_normalize_goal_match_event():
    m_id = uuid.uuid4()
    p_id = uuid.uuid4()
    c_id = uuid.uuid4()
    a_id = uuid.uuid4()

    event = MatchEvent(
        id=uuid.uuid4(),
        match_id=m_id,
        club_id=c_id,
        player_id=p_id,
        assist_player_id=a_id,
        event_type="GOAL",
        event_detail="Normal Goal",
        minute=34,
        extra_minute=None,
        comments=None,
        event_key="34_0_goal_123",
        provider_event_id="pe_123",
    )

    actions = normalize_match_event(event)
    assert len(actions) == 2

    # Scorer action
    scorer_act = actions[0]
    assert scorer_act.player_id == p_id
    assert scorer_act.action_type == ActionType.SHOOTING.value
    assert scorer_act.action_subtype == ActionSubtype.GOAL.value
    assert scorer_act.outcome == ActionOutcome.SUCCESS.value
    assert scorer_act.minute == 34
    assert scorer_act.x is None
    assert scorer_act.y is None

    # Assist action
    assist_act = actions[1]
    assert assist_act.player_id == a_id
    assert assist_act.recipient_player_id == p_id
    assert assist_act.action_type == ActionType.CREATION.value
    assert assist_act.action_subtype == ActionSubtype.ASSIST.value
    assert assist_act.outcome == ActionOutcome.SUCCESS.value


def test_normalize_penalty_goal_event():
    event = MatchEvent(
        id=uuid.uuid4(),
        match_id=uuid.uuid4(),
        club_id=uuid.uuid4(),
        player_id=uuid.uuid4(),
        assist_player_id=None,
        event_type="GOAL",
        event_detail="Penalty",
        minute=75,
        event_key="75_0_pen",
    )
    actions = normalize_match_event(event)
    assert len(actions) == 1
    assert actions[0].action_subtype == ActionSubtype.PENALTY_GOAL.value


def test_normalize_card_event():
    event = MatchEvent(
        id=uuid.uuid4(),
        match_id=uuid.uuid4(),
        club_id=uuid.uuid4(),
        player_id=uuid.uuid4(),
        event_type="CARD",
        event_detail="Yellow Card",
        minute=19,
        event_key="19_0_yellow",
    )
    actions = normalize_match_event(event)
    assert len(actions) == 1
    assert actions[0].action_type == ActionType.DISCIPLINE.value
    assert actions[0].action_subtype == ActionSubtype.YELLOW_CARD.value


def test_normalize_player_match_stats():
    pms = PlayerMatchStats(
        id=uuid.uuid4(),
        match_id=uuid.uuid4(),
        club_id=uuid.uuid4(),
        player_id=uuid.uuid4(),
        position="M",
        minutes=90,
        passes_total=40,
        pass_accuracy=80.0,
        passes_key=3,
        shots_total=2,
        shots_on_target=1,
        tackles_total=2,
        interceptions=1,
        blocks=1,
        duels_total=6,
        duels_won=4,
        dribbles_attempts=2,
        dribbles_success=2,
        fouls_committed=1,
        fouls_drawn=2,
    )

    actions = normalize_player_match_stats(pms)
    assert len(actions) > 0

    subtypes = {a.action_subtype: a for a in actions}

    # Verify pass breakdown: 80% of 40 = 32 completed, 8 incomplete
    assert ActionSubtype.PASS_COMPLETED.value in subtypes
    assert subtypes[ActionSubtype.PASS_COMPLETED.value].action_quantity == 32
    assert ActionSubtype.PASS_INCOMPLETE.value in subtypes
    assert subtypes[ActionSubtype.PASS_INCOMPLETE.value].action_quantity == 8

    # Verify key passes
    assert ActionSubtype.KEY_PASS.value in subtypes
    assert subtypes[ActionSubtype.KEY_PASS.value].action_quantity == 3

    # Verify defending
    assert ActionSubtype.TACKLE.value in subtypes
    assert subtypes[ActionSubtype.TACKLE.value].action_quantity == 2

    # Verify no coordinates fabricated
    for a in actions:
        assert a.x is None
        assert a.y is None
