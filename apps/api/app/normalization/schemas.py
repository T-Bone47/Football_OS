from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NormalizedCompetition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_id: str
    name: str
    country: str
    code: str | None = None
    type: str = "LEAGUE"


class NormalizedSeason(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    start_year: int
    end_year: int
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False


class NormalizedClub(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_id: str
    name: str
    code: str | None = None
    country: str
    founded: int | None = None
    venue_name: str | None = None
    venue_capacity: int | None = None
    logo_url: str | None = None


class NormalizedPlayer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_id: str
    name: str
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    height_cm: int | None = None
    weight_kg: int | None = None
    primary_position: str | None = None
    photo_url: str | None = None


class NormalizedPlayerStats(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_player_id: str
    provider_club_id: str | None = None
    provider_league_id: str
    season_year: int
    appearances: int = 0
    lineups: int = 0
    minutes: int = 0
    position: str | None = None
    rating: float | None = None
    goals: int = 0
    assists: int = 0
    conceded: int = 0
    raw_stats: dict[str, Any] = {}


class NormalizedScoreDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    home: int | None = None
    away: int | None = None


class NormalizedScore(BaseModel):
    model_config = ConfigDict(extra="ignore")

    halftime: NormalizedScoreDetail = NormalizedScoreDetail()
    fulltime: NormalizedScoreDetail = NormalizedScoreDetail()
    extratime: NormalizedScoreDetail = NormalizedScoreDetail()
    penalty: NormalizedScoreDetail = NormalizedScoreDetail()


class NormalizedFixture(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_fixture_id: str
    date: datetime
    timestamp: int | None = None
    status: str
    status_detail: str | None = None
    elapsed: int | None = None
    round: str | None = None
    stage: str | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    referee: str | None = None
    provider_league_id: str
    league_name: str
    league_country: str
    season_year: int
    home_provider_club_id: str
    home_club_name: str
    home_club_logo: str | None = None
    home_winner: bool | None = None
    away_provider_club_id: str
    away_club_name: str
    away_club_logo: str | None = None
    away_winner: bool | None = None
    home_score: int | None = None
    away_score: int | None = None
    score: NormalizedScore = NormalizedScore()


class NormalizedMatchEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_fixture_id: str
    provider_club_id: str
    club_name: str | None = None
    provider_player_id: str | None = None
    player_name: str | None = None
    provider_assist_id: str | None = None
    assist_name: str | None = None
    event_type: str  # GOAL, CARD, SUBSTITUTION, VAR, OTHER
    event_detail: str | None = None
    minute: int
    extra_minute: int | None = None
    comments: str | None = None
    event_key: str
    provider_event_id: str | None = None


class NormalizedMatchLineup(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_fixture_id: str
    provider_club_id: str
    club_name: str | None = None
    formation: str | None = None
    coach_name: str | None = None
    provider_player_id: str
    player_name: str
    jersey_number: int | None = None
    position: str | None = None
    grid: str | None = None
    is_starter: bool = True
    is_captain: bool = False


class NormalizedMatchStatistics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_fixture_id: str
    provider_club_id: str
    club_name: str | None = None
    possession_pct: float | None = None
    shots_total: int | None = None
    shots_on_target: int | None = None
    shots_off_target: int | None = None
    blocked_shots: int | None = None
    shots_inside_box: int | None = None
    shots_outside_box: int | None = None
    fouls: int | None = None
    corners: int | None = None
    offsides: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    saves: int | None = None
    passes_total: int | None = None
    passes_accurate: int | None = None
    pass_accuracy_pct: float | None = None
    expected_goals: float | None = None
    free_kicks: int | None = None
    raw_stats: dict[str, Any] = {}


class NormalizedPlayerMatchStats(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_fixture_id: str
    provider_club_id: str
    club_name: str | None = None
    provider_player_id: str
    player_name: str
    photo_url: str | None = None

    # Lineup / Role context
    is_starter: bool | None = None
    is_substitute: bool | None = None
    is_captain: bool = False
    position: str | None = None
    jersey_number: int | None = None
    grid: str | None = None

    # Playing time & rating
    minutes: int | None = None
    rating: float | None = None

    # Attacking
    goals: int | None = None
    assists: int | None = None
    shots_total: int | None = None
    shots_on_target: int | None = None
    offsides: int | None = None

    # Passing
    passes_total: int | None = None
    passes_key: int | None = None
    pass_accuracy: float | None = None

    # Defending & Duels
    tackles_total: int | None = None
    blocks: int | None = None
    interceptions: int | None = None
    duels_total: int | None = None
    duels_won: int | None = None

    # Dribbles
    dribbles_attempts: int | None = None
    dribbles_success: int | None = None
    dribbles_past: int | None = None

    # Discipline
    fouls_drawn: int | None = None
    fouls_committed: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None

    # Penalties
    penalties_won: int | None = None
    penalties_committed: int | None = None
    penalties_scored: int | None = None
    penalties_missed: int | None = None
    penalties_saved: int | None = None

    # Goalkeeping
    saves: int | None = None
    goals_conceded: int | None = None
    clean_sheet: bool | None = None

    # Raw stats payload
    raw_stats: dict[str, Any] = {}

