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


