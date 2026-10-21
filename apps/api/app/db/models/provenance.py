"""Provenance foundation (architecture doc §14/§17): every important record
traces back through IngestionRun -> DataSource, and every raw payload is
content-addressed via DataSnapshot before anything downstream touches it.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
    """A provider we ingest from, with its licensing / attribution policy.

    `enabled = false` means "do not ingest from this source" even if a capability row
    exists. `redistribution_allowed` records whether the source's terms permit storing
    and re-serving the data inside this product.
    """

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512))
    license: Mapped[str | None] = mapped_column(String(256))
    license_url: Mapped[str | None] = mapped_column(String(512))
    attribution: Mapped[str | None] = mapped_column(String(256))
    redistribution_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    terms_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ingestion_runs: Mapped[list["IngestionRun"]] = relationship(back_populates="data_source")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCESS','PARTIAL','FAILED')",
            name="ck_ingestion_runs_status",
        ),
        Index("ix_ingestion_runs_data_source_status", "data_source_id", "status"),
    )

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
    __table_args__ = (
        CheckConstraint(
            "validation_status IN ('PENDING','VALID','INVALID')",
            name="ck_data_snapshots_validation_status",
        ),
        UniqueConstraint("ingestion_run_id", "sha256", name="uq_snapshot_run_sha"),
    )

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

    ingestion_run: Mapped["IngestionRun"] = relationship(back_populates="snapshots")
