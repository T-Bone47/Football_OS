"""Durable operational state (migration 0015): collections with ownership columns, and an append-only ledger."""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class OperationalRecord(Base):
    """One domain object (project, watchlist, scenario, alert, job ...) with indexed ownership for tenant isolation."""

    __tablename__ = "operational_records"
    __table_args__ = (
        Index("ix_operational_records_collection_org", "collection", "organization_id"),
        Index("ix_operational_records_collection_owner", "collection", "owner_id"),
    )

    collection: Mapped[str] = mapped_column(String(32), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128))
    organization_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LedgerEntry(Base):
    """Append-only evidence (decision records, audit events), hash-chained per ledger; UPDATE/DELETE are rejected by a trigger."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint("ledger_key", "seq", name="uq_ledger_entries_key_seq"),
        UniqueConstraint("entry_kind", "entry_id", name="uq_ledger_entries_kind_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ledger_key: Mapped[str] = mapped_column(String(160))
    seq: Mapped[int] = mapped_column(Integer)
    entry_kind: Mapped[str] = mapped_column(String(32))
    entry_id: Mapped[str] = mapped_column(String(64))
    organization_id: Mapped[str | None] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(String(64), server_default="")
    entry_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
