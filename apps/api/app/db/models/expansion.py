"""Expansion-layer canonical models (database expansion, Phase 1).

These tables extend — they never replace — the existing canonical entities:

* ``player_aliases``              — name history and source-native spellings.
* ``player_club_memberships``     — time-bounded club registrations.
* ``ingestion_checkpoints``       — durable, resumable ingestion state.
* ``ingestion_failures``          — retry queue + dead-letter records.
* ``field_provenance``            — per-field provider provenance.
* ``source_conflicts``            — unresolved provider disagreements.
* ``identity_review_queue``       — ambiguous cross-provider identity candidates.
* ``country_priorities``          — dated, configurable country-priority registry.

Every table keeps provider identity, confidence and provenance so that no downstream
consumer has to guess where a value came from.
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


class CompetitionIdentity(Base):
    """Provider identity for a canonical competition.

    The canonical `competitions` table is provider-neutral (a league is a league), so
    the provider's own competition id has to live in an explicit mapping table —
    exactly like `player_identities` and `club_identities`. A provider competition id
    is never assumed to equal a canonical id.
    """

    __tablename__ = "competition_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_competition_id", name="uq_competition_identity_provider_id"
        ),
        Index("ix_competition_identities_competition_id", "competition_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    resolution_method: Mapped[str] = mapped_column(
        String(64), nullable=False, default="DIRECT_PROVIDER_ID"
    )
    source_url: Mapped[str | None] = mapped_column(String(512))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlayerAlias(Base):
    """A name this player is known by (source spelling, transliteration, surname change).

    The canonical `players.name` stays the display name; every other observed spelling is
    kept here so that a later provider can be matched without destroying the original
    Unicode or accents.
    """

    __tablename__ = "player_aliases"
    __table_args__ = (
        UniqueConstraint("player_id", "provider", "alias", name="uq_player_alias_provider_alias"),
        Index("ix_player_aliases_player_id", "player_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(160), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False, default="SOURCE_NAME")
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_entity_id: Mapped[str | None] = mapped_column(String(128))
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    player: Mapped["Player"] = relationship(back_populates="aliases")  # type: ignore[name-defined]


class PlayerClubMembership(Base):
    """A time-bounded association between a player and a club.

    A player's current club is one of these rows (plus the denormalised
    `players.club_id` pointer). History is never overwritten by a later club.
    """

    __tablename__ = "player_club_memberships"
    __table_args__ = (
        UniqueConstraint("source_provider", "source_record_id", name="uq_player_membership_source_record"),
        Index("ix_player_club_memberships_player_id", "player_id"),
        Index("ix_player_club_memberships_club_id", "club_id"),
        Index("ix_player_club_memberships_competition_season_id", "competition_season_id"),
        Index("ix_player_club_memberships_is_current", "is_current"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL")
    )
    competition_season_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competition_seasons.id", ondelete="SET NULL")
    )
    membership_type: Mapped[str] = mapped_column(String(32), nullable=False, default="REGISTRATION")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(String(512))
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IngestionCheckpoint(Base):
    """Durable ingestion state for one provider scope.

    The scope key is the exact parameter set of a provider query minus the page number, so
    a checkpoint can never be reused for a different league, season or team.
    """

    __tablename__ = "ingestion_checkpoints"
    __table_args__ = (
        UniqueConstraint("provider", "entity_type", "scope_key", name="uq_ingestion_checkpoint_scope"),
        Index("ix_ingestion_checkpoints_status", "status"),
        Index("ix_ingestion_checkpoints_provider", "provider", "entity_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(256), nullable=False)
    competition: Mapped[str | None] = mapped_column(String(128))
    season: Mapped[str | None] = mapped_column(String(16))
    page: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    records_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    declared_total_pages: Mapped[int | None] = mapped_column(Integer)
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IngestionFailure(Base):
    """Retry queue and dead-letter store for records that could not be ingested."""

    __tablename__ = "ingestion_failures"
    __table_args__ = (
        UniqueConstraint(
            "provider", "resource", "scope_key", "record_key", name="uq_ingestion_failure_record"
        ),
        Index("ix_ingestion_failures_status", "status"),
        Index("ix_ingestion_failures_provider", "provider", "resource"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(256), nullable=False)
    record_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="TRANSIENT")
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FieldProvenance(Base):
    """Which provider supplied which field of which canonical entity, and how."""

    __tablename__ = "field_provenance"
    __table_args__ = (
        UniqueConstraint(
            "entity_type", "entity_id", "field_name", "provider", name="uq_field_provenance_field"
        ),
        Index("ix_field_provenance_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_entity_id: Mapped[str | None] = mapped_column(String(128))
    source_value: Mapped[dict | None] = mapped_column(JSONB)
    transformation: Mapped[str | None] = mapped_column(String(128))
    source_hash: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float | None] = mapped_column(Float)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceConflict(Base):
    """A provider disagreement that the resolution policy did not settle silently."""

    __tablename__ = "source_conflicts"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "field_name", name="uq_source_conflict_field"),
        Index("ix_source_conflicts_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    candidates: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    resolution: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IdentityReviewItem(Base):
    """An ambiguous cross-provider identity candidate awaiting human review.

    Nothing is merged automatically from this table: an approved row is applied by an
    explicit, reversible merge operation.
    """

    __tablename__ = "identity_review_queue"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_entity_id", "candidate_player_id",
            name="uq_identity_review_candidate",
        ),
        Index("ix_identity_review_queue_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_entity_id: Mapped[str] = mapped_column(String(160), nullable=False)
    candidate_player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    match_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CountryPriority(Base):
    """Dated country-priority registry (national-team countries, not club leagues).

    `ranking_source` and `ranking_snapshot_date` make the selection auditable: the
    registry is a snapshot, not a permanent hardcoded list.
    """

    __tablename__ = "country_priorities"
    __table_args__ = (
        UniqueConstraint("country_code", name="uq_country_priority_code"),
        Index("ix_country_priorities_rank", "rank"),
        Index("ix_country_priorities_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_code: Mapped[str] = mapped_column(String(8), nullable=False)
    country_name: Mapped[str] = mapped_column(String(64), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    ranking_source: Mapped[str] = mapped_column(String(256), nullable=False)
    ranking_snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    scope_label: Mapped[str] = mapped_column(String(64), nullable=False, default="FIFA_MENS_SENIOR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
