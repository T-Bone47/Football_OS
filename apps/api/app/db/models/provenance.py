"""Provenance foundation (architecture doc §14/§17): every important record
traces back through IngestionRun -> DataSource, and every raw payload is
content-addressed via DataSnapshot before anything downstream touches it.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class IngestionStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ValidationStatus(str, enum.Enum):
    PENDING = "PENDING"
    VALID = "VALID"
    INVALID = "INVALID"


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512))
    license: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ingestion_runs: Mapped[list["IngestionRun"]] = relationship(back_populates="data_source")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (Index("ix_ingestion_runs_data_source_status", "data_source_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(256), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[IngestionStatus] = mapped_column(
        SAEnum(IngestionStatus, name="ingestion_run_status", native_enum=False, length=16, validate_strings=True),
        default=IngestionStatus.QUEUED,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    record_count: Mapped[int | None] = mapped_column(Integer)

    data_source: Mapped["DataSource"] = relationship(back_populates="ingestion_runs")
    snapshots: Mapped[list["DataSnapshot"]] = relationship(back_populates="ingestion_run")


class DataSnapshot(Base):
    __tablename__ = "data_snapshots"
    __table_args__ = (UniqueConstraint("ingestion_run_id", "sha256", name="uq_snapshot_run_sha"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_location: Mapped[str] = mapped_column(String(1024), nullable=False)
    schema_version: Mapped[str | None] = mapped_column(String(32))
    validation_status: Mapped[ValidationStatus] = mapped_column(
        SAEnum(ValidationStatus, name="data_snapshot_validation_status", native_enum=False, length=16, validate_strings=True),
        default=ValidationStatus.PENDING,
        nullable=False,
    )
    validation_errors: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Phase 17 (migration 0014): what the provider actually returned, so a
    # snapshot can be traced to a request rather than to an insert time.
    provider_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(String(1024))

    ingestion_run: Mapped["IngestionRun"] = relationship(back_populates="snapshots")
