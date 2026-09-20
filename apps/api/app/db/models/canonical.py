"""Canonical football entities (Silver layer, architecture doc §20/§21).
All entities are normalized from raw Bronze snapshots, carry explicit
identity mappings back to external providers, and link to DataSnapshot
for end-to-end data provenance.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str | None] = mapped_column(String(32))
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="LEAGUE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    seasons: Mapped[list["CompetitionSeason"]] = relationship(back_populates="competition")


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("name", name="uq_season_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. "2023" or "2023/2024"
    start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    end_year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    competitions: Mapped[list["CompetitionSeason"]] = relationship(back_populates="season")


class CompetitionSeason(Base):
    __tablename__ = "competition_seasons"
    __table_args__ = (
        UniqueConstraint("competition_id", "season_id", name="uq_competition_season"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    season_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    competition: Mapped["Competition"] = relationship(back_populates="seasons")
    season: Mapped["Season"] = relationship(back_populates="competitions")
    matches: Mapped[list["Match"]] = relationship(back_populates="competition_season")


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str | None] = mapped_column(String(16))
    country: Mapped[str] = mapped_column(String(64), nullable=False)
    founded: Mapped[int | None] = mapped_column(Integer)
    venue_name: Mapped[str | None] = mapped_column(String(128))
    venue_capacity: Mapped[int | None] = mapped_column(Integer)
    logo_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    identities: Mapped[list["ClubIdentity"]] = relationship(back_populates="club", cascade="all, delete-orphan")
    season_stats: Mapped[list["PlayerSeasonStats"]] = relationship(back_populates="club")
    player_match_stats: Mapped[list["PlayerMatchStats"]] = relationship(back_populates="club")


class ClubIdentity(Base):
    __tablename__ = "club_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_club_id", name="uq_club_identity_provider_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_club_id: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    resolution_method: Mapped[str] = mapped_column(
        String(64), nullable=False, default="DIRECT_PROVIDER_ID"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    club: Mapped["Club"] = relationship(back_populates="identities")


class Player(Base):
    __tablename__ = "players"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(64))
    last_name: Mapped[str | None] = mapped_column(String(64))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(64))
    height_cm: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[int | None] = mapped_column(Integer)
    primary_position: Mapped[str | None] = mapped_column(String(32))
    photo_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    identities: Mapped[list["PlayerIdentity"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    season_stats: Mapped[list["PlayerSeasonStats"]] = relationship(back_populates="player")
    match_stats: Mapped[list["PlayerMatchStats"]] = relationship(back_populates="player")
    role_profiles: Mapped[list["PlayerRoleProfile"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    tactical_fits: Mapped[list["PlayerTacticalFit"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )


class PlayerIdentity(Base):
    __tablename__ = "player_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_player_id", name="uq_player_identity_provider_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_player_id: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    resolution_method: Mapped[str] = mapped_column(
        String(64), nullable=False, default="DIRECT_PROVIDER_ID"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    player: Mapped["Player"] = relationship(back_populates="identities")


class PlayerSeasonStats(Base):
    __tablename__ = "player_season_stats"
    __table_args__ = (
        UniqueConstraint("player_id", "club_id", "competition_season_id", name="uq_player_club_comp_season"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL")
    )
    competition_season_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competition_seasons.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_snapshots.id", ondelete="SET NULL")
    )

    appearances: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lineups: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position: Mapped[str | None] = mapped_column(String(32))
    rating: Mapped[float | None] = mapped_column(Float)
    goals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assists: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conceded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_stats: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    player: Mapped["Player"] = relationship(back_populates="season_stats")
    club: Mapped["Club | None"] = relationship(back_populates="season_stats")
    competition_season: Mapped["CompetitionSeason"] = relationship()


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("competition_season_id", "home_club_id", "away_club_id", "date", name="uq_match_fixture"),
        UniqueConstraint("provider", "provider_fixture_id", name="uq_match_provider_fixture"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(
        String(64), nullable=False, default="api-football", server_default="api-football"
    )
    provider_fixture_id: Mapped[str | None] = mapped_column(String(128), index=True)
    competition_season_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competition_seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    home_club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    away_club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SCHEDULED", index=True)
    status_detail: Mapped[str | None] = mapped_column(String(64))
    round: Mapped[str | None] = mapped_column(String(128))
    stage: Mapped[str | None] = mapped_column(String(64))
    venue_name: Mapped[str | None] = mapped_column(String(255))
    venue_city: Mapped[str | None] = mapped_column(String(128))
    referee: Mapped[str | None] = mapped_column(String(128))
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    halftime_home_score: Mapped[int | None] = mapped_column(Integer)
    halftime_away_score: Mapped[int | None] = mapped_column(Integer)
    fulltime_home_score: Mapped[int | None] = mapped_column(Integer)
    fulltime_away_score: Mapped[int | None] = mapped_column(Integer)
    extratime_home_score: Mapped[int | None] = mapped_column(Integer)
    extratime_away_score: Mapped[int | None] = mapped_column(Integer)
    penalty_home_score: Mapped[int | None] = mapped_column(Integer)
    penalty_away_score: Mapped[int | None] = mapped_column(Integer)
    winner_club_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL")
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_snapshots.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    competition_season: Mapped["CompetitionSeason"] = relationship(back_populates="matches")
    home_club: Mapped["Club"] = relationship(foreign_keys=[home_club_id])
    away_club: Mapped["Club"] = relationship(foreign_keys=[away_club_id])
    winner_club: Mapped["Club | None"] = relationship(foreign_keys=[winner_club_id])
    teams: Mapped[list["MatchTeam"]] = relationship(back_populates="match", cascade="all, delete-orphan")
    events: Mapped[list["MatchEvent"]] = relationship(
        back_populates="match", cascade="all, delete-orphan", order_by="MatchEvent.minute"
    )
    lineups: Mapped[list["MatchLineup"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    statistics: Mapped[list["MatchStatistics"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    player_stats: Mapped[list["PlayerMatchStats"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class MatchTeam(Base):
    __tablename__ = "match_teams"
    __table_args__ = (
        UniqueConstraint("match_id", "club_id", name="uq_match_team_match_club"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opponent_club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    result: Mapped[str | None] = mapped_column(String(16))
    goals_for: Mapped[int | None] = mapped_column(Integer)
    goals_against: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="teams")
    club: Mapped["Club"] = relationship(foreign_keys=[club_id])
    opponent_club: Mapped["Club"] = relationship(foreign_keys=[opponent_club_id])


class MatchEvent(Base):
    __tablename__ = "match_events"
    __table_args__ = (
        UniqueConstraint("match_id", "event_key", name="uq_match_event_match_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), index=True
    )
    assist_player_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)  # GOAL, CARD, SUBSTITUTION, VAR, OTHER
    event_detail: Mapped[str | None] = mapped_column(String(64))
    minute: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    extra_minute: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[str | None] = mapped_column(String(255))
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_event_id: Mapped[str | None] = mapped_column(String(128), index=True)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_snapshots.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="events")
    club: Mapped["Club"] = relationship()
    player: Mapped["Player | None"] = relationship(foreign_keys=[player_id])
    assist_player: Mapped["Player | None"] = relationship(foreign_keys=[assist_player_id])


class MatchLineup(Base):
    __tablename__ = "match_lineups"
    __table_args__ = (
        UniqueConstraint("match_id", "club_id", "player_id", name="uq_match_lineup_player"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_starter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    jersey_number: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[str | None] = mapped_column(String(16))  # G, D, M, F
    formation_position: Mapped[str | None] = mapped_column(String(16))  # e.g. "1:1"
    formation: Mapped[str | None] = mapped_column(String(32))  # e.g. "3-4-2-1"
    is_captain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    coach_name: Mapped[str | None] = mapped_column(String(128))
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_snapshots.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="lineups")
    club: Mapped["Club"] = relationship()
    player: Mapped["Player"] = relationship()


class MatchStatistics(Base):
    __tablename__ = "match_statistics"
    __table_args__ = (
        UniqueConstraint("match_id", "club_id", name="uq_match_statistics_match_club"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    possession_pct: Mapped[float | None] = mapped_column(Float)
    shots_total: Mapped[int | None] = mapped_column(Integer)
    shots_on_target: Mapped[int | None] = mapped_column(Integer)
    shots_off_target: Mapped[int | None] = mapped_column(Integer)
    blocked_shots: Mapped[int | None] = mapped_column(Integer)
    shots_inside_box: Mapped[int | None] = mapped_column(Integer)
    shots_outside_box: Mapped[int | None] = mapped_column(Integer)
    fouls: Mapped[int | None] = mapped_column(Integer)
    corners: Mapped[int | None] = mapped_column(Integer)
    offsides: Mapped[int | None] = mapped_column(Integer)
    yellow_cards: Mapped[int | None] = mapped_column(Integer)
    red_cards: Mapped[int | None] = mapped_column(Integer)
    saves: Mapped[int | None] = mapped_column(Integer)
    passes_total: Mapped[int | None] = mapped_column(Integer)
    passes_accurate: Mapped[int | None] = mapped_column(Integer)
    pass_accuracy_pct: Mapped[float | None] = mapped_column(Float)
    expected_goals: Mapped[float | None] = mapped_column(Float)
    free_kicks: Mapped[int | None] = mapped_column(Integer)
    raw_stats: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_snapshots.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="statistics")
    club: Mapped["Club"] = relationship()


class PlayerMatchStats(Base):
    __tablename__ = "player_match_stats"
    __table_args__ = (
        UniqueConstraint("match_id", "club_id", "player_id", name="uq_player_match_stats"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(
        String(64), nullable=False, default="api-football", server_default="api-football"
    )
    provider_player_id: Mapped[str | None] = mapped_column(String(128), index=True)
    provider_fixture_id: Mapped[str | None] = mapped_column(String(128), index=True)
    provider_club_id: Mapped[str | None] = mapped_column(String(128), index=True)

    # Lineup / Role context
    is_starter: Mapped[bool | None] = mapped_column(Boolean)
    is_substitute: Mapped[bool | None] = mapped_column(Boolean)
    position: Mapped[str | None] = mapped_column(String(16))  # G, D, M, F
    jersey_number: Mapped[int | None] = mapped_column(Integer)
    formation_position: Mapped[str | None] = mapped_column(String(16))  # grid position if available
    is_captain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Playing time & rating
    minutes: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[float | None] = mapped_column(Float)

    # Attacking
    goals: Mapped[int | None] = mapped_column(Integer)
    assists: Mapped[int | None] = mapped_column(Integer)
    shots_total: Mapped[int | None] = mapped_column(Integer)
    shots_on_target: Mapped[int | None] = mapped_column(Integer)
    offsides: Mapped[int | None] = mapped_column(Integer)

    # Passing
    passes_total: Mapped[int | None] = mapped_column(Integer)
    passes_key: Mapped[int | None] = mapped_column(Integer)
    pass_accuracy: Mapped[float | None] = mapped_column(Float)

    # Defending & Duels
    tackles_total: Mapped[int | None] = mapped_column(Integer)
    blocks: Mapped[int | None] = mapped_column(Integer)
    interceptions: Mapped[int | None] = mapped_column(Integer)
    duels_total: Mapped[int | None] = mapped_column(Integer)
    duels_won: Mapped[int | None] = mapped_column(Integer)

    # Dribbles
    dribbles_attempts: Mapped[int | None] = mapped_column(Integer)
    dribbles_success: Mapped[int | None] = mapped_column(Integer)
    dribbles_past: Mapped[int | None] = mapped_column(Integer)

    # Discipline
    fouls_drawn: Mapped[int | None] = mapped_column(Integer)
    fouls_committed: Mapped[int | None] = mapped_column(Integer)
    yellow_cards: Mapped[int | None] = mapped_column(Integer)
    red_cards: Mapped[int | None] = mapped_column(Integer)

    # Penalties
    penalties_won: Mapped[int | None] = mapped_column(Integer)
    penalties_committed: Mapped[int | None] = mapped_column(Integer)
    penalties_scored: Mapped[int | None] = mapped_column(Integer)
    penalties_missed: Mapped[int | None] = mapped_column(Integer)
    penalties_saved: Mapped[int | None] = mapped_column(Integer)

    # Goalkeeping
    saves: Mapped[int | None] = mapped_column(Integer)
    goals_conceded: Mapped[int | None] = mapped_column(Integer)
    clean_sheet: Mapped[bool | None] = mapped_column(Boolean)

    # Raw stats payload & Provenance
    raw_stats: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_snapshots.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="player_stats")
    club: Mapped["Club"] = relationship(back_populates="player_match_stats")
    player: Mapped["Player"] = relationship(back_populates="match_stats")


class FeatureSnapshot(Base):
    """Canonical analytical feature snapshot (Phase 2 Slice 1).
    Stores leakage-safe, versioned, reproducible feature vectors for players,
    teams, and matches as of a strictly defined pre-event timestamp.
    """
    __tablename__ = "feature_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "feature_set",
            "calculation_version",
            "as_of",
            name="uq_feature_snapshot",
        ),
        Index("ix_feature_snapshots_entity", "entity_type", "entity_id"),
        Index("ix_feature_snapshots_as_of", "as_of"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'player', 'team', 'match'
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    match_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    feature_set: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. 'player_match_v1'
    calculation_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    season_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    competition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    match: Mapped["Match | None"] = relationship()
    season: Mapped["Season | None"] = relationship()
    competition: Mapped["Competition | None"] = relationship()


class PlayerRoleProfile(Base):
    """Canonical Player Role Profile (Phase 2 Slice 2).
    Stores continuous functional role tendencies, data-driven archetypes,
    and standardized feature vectors derived from leakage-safe FeatureSnapshots.
    """
    __tablename__ = "player_role_profiles"
    __table_args__ = (
        UniqueConstraint("player_id", "feature_set_version", "as_of", name="uq_player_role_profile"),
        Index("ix_player_role_profiles_player_id", "player_id"),
        Index("ix_player_role_profiles_as_of", "as_of"),
        Index("ix_player_role_profiles_position_group", "position_group"),
        Index("ix_player_role_profiles_primary_archetype", "primary_archetype"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False, default="role_feature_set_v1")
    role_status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUALIFIED")  # 'QUALIFIED', 'INSUFFICIENT_SAMPLE'
    sample_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sample_matches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position_group: Mapped[str] = mapped_column(String(16), nullable=False)  # 'GK', 'DEF', 'MID', 'ATT'

    primary_archetype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    secondary_archetype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    archetype_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Continuous dimensional scores (0.0 - 1.0)
    profile_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    # Standardized feature vector used for similarity & clustering
    feature_vector: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    # Provenance metadata (source snapshot ids, cluster version, scaler params)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    player: Mapped["Player"] = relationship(back_populates="role_profiles")


class PlayerTacticalFit(Base):
    """Canonical Player Tactical Fit (Phase 2 Slice 3).
    Stores deterministic compatibility between a player's functional tendencies,
    a specific tactical system, formation, position, and role requirement.
    """
    __tablename__ = "player_tactical_fits"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "tactical_context_id",
            "feature_set_version",
            "calculation_version",
            "as_of",
            name="uq_player_tactical_fit",
        ),
        Index("ix_player_tactical_fits_player_id", "player_id"),
        Index("ix_player_tactical_fits_as_of", "as_of"),
        Index("ix_player_tactical_fits_tactical_context_id", "tactical_context_id"),
        Index("ix_player_tactical_fits_target_role", "target_role"),
        Index("ix_player_tactical_fits_fit_status", "fit_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tactical_context_id: Mapped[str] = mapped_column(String(64), nullable=False)
    formation: Mapped[str] = mapped_column(String(32), nullable=False)
    target_position: Mapped[str] = mapped_column(String(16), nullable=False)
    position_group: Mapped[str] = mapped_column(String(16), nullable=False)  # 'GK', 'DEF', 'MID', 'ATT'
    target_role: Mapped[str] = mapped_column(String(64), nullable=False)

    # Core scores [0.0, 1.0]
    fit_score: Mapped[float] = mapped_column(Float, nullable=False)
    position_fit: Mapped[float] = mapped_column(Float, nullable=False)
    role_fit: Mapped[float] = mapped_column(Float, nullable=False)
    dimension_fit: Mapped[float] = mapped_column(Float, nullable=False)
    style_fit: Mapped[float | None] = mapped_column(Float, nullable=True)
    contextual_fit: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Evidence, Uncertainty, and Confidence
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)  # 'HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT_DATA'
    fit_status: Mapped[str] = mapped_column(String(32), nullable=False)  # 'FIT', 'MODERATE_FIT', 'POOR_FIT', 'INSUFFICIENT_DATA'

    # Analytical breakdown and factual explanations
    dimension_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    why_fit: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    why_not_fit: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    # Versioning and Provenance
    calculation_version: Mapped[str] = mapped_column(String(32), nullable=False, default="tactical_fit_v1")
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False, default="role_feature_set_v1")
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    player: Mapped["Player"] = relationship(back_populates="tactical_fits")
    team: Mapped["Club | None"] = relationship()
    season: Mapped["Season | None"] = relationship()




