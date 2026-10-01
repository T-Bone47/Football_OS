"""Phase 17 persistent operational state (migration 0014).

Phases 10-16 kept operational state in module-level dicts that vanished on
restart. Everything here is a PostgreSQL row so status endpoints can report
what was actually observed. Three tables are append-only at the database
level (triggers in 0014): ops_inference_log, ops_decisions and
ops_audit_events.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProviderProbe(Base):
    """One real connectivity check against a provider endpoint (§3)."""

    __tablename__ = "ops_provider_probes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    authentication_state: Mapped[str] = mapped_column(String(32), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    quota: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    capability: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    probed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ContractFingerprint(Base):
    """Registered field-set contract for a provider resource (§39)."""

    __tablename__ = "ops_contract_fingerprints"
    __table_args__ = (UniqueConstraint("provider", "resource", name="uq_contract_provider_resource"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    field_types: Mapped[dict] = mapped_column(JSONB, nullable=False)
    registered_from_snapshot: Mapped[str | None] = mapped_column(String(64))
    registered_at: Mapped[datetime] = _created()


class JobRun(Base):
    """Every scheduled or on-demand execution (§7)."""

    __tablename__ = "ops_job_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    schedule_class: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    resource: Mapped[str | None] = mapped_column(String(64))
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[float | None] = mapped_column(Float)
    records: Mapped[int | None] = mapped_column(Integer)
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    snapshot_sha256: Mapped[str | None] = mapped_column(String(64))


class QualityReport(Base):
    """DataQualityReport for one snapshot or Silver scope (§10)."""

    __tablename__ = "ops_quality_reports"

    id: Mapped[uuid.UUID] = _uuid_pk()
    scope: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    snapshot_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    overall: Mapped[str] = mapped_column(String(8), nullable=False)
    checks: Mapped[list] = mapped_column(JSONB, nullable=False)
    records_examined: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _created()


class FeatureRefreshRecord(Base):
    """One feature refresh decision (§12)."""

    __tablename__ = "ops_feature_refresh"

    id: Mapped[uuid.UUID] = _uuid_pk()
    feature: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_dependency: Mapped[str] = mapped_column(String(256), nullable=False)
    previous_version: Mapped[str | None] = mapped_column(String(64))
    new_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelRegistryEntry(Base):
    """Models that may be served. Only rows here can produce a prediction."""

    __tablename__ = "ops_model_registry"
    __table_args__ = (UniqueConstraint("model_id", "model_version", name="uq_ops_model_version"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    data_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    supported_competitions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    deployment_state: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    min_history_matches: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_feature_age_hours: Mapped[float | None] = mapped_column(Float)
    registered_at: Mapped[datetime] = _created()


class InferenceLog(Base):
    """Every inference request, served or refused. Immutable (trigger)."""

    __tablename__ = "ops_inference_log"

    id: Mapped[uuid.UUID] = _uuid_pk()
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prediction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model_id: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(64))
    feature_version: Mapped[str | None] = mapped_column(String(64))
    dataset_version: Mapped[str | None] = mapped_column(String(128))
    data_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    competition: Mapped[str | None] = mapped_column(String(128), index=True)
    subject_id: Mapped[str | None] = mapped_column(String(128), index=True)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    output: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    features_used: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    missing_features: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)
    is_ood: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _created()


class OutcomeRecord(Base):
    """A realized result linked to an inference. Never edits the inference."""

    __tablename__ = "ops_outcomes"
    __table_args__ = (UniqueConstraint("inference_id", name="uq_outcome_inference"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    inference_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ops_inference_log.id", ondelete="RESTRICT"), nullable=False
    )
    realized: Mapped[dict] = mapped_column(JSONB, nullable=False)
    outcome_source: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome_snapshot_sha256: Mapped[str | None] = mapped_column(String(64))
    observation_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evaluation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evaluated_at: Mapped[datetime] = _created()


class Organization(Base):
    __tablename__ = "ops_organizations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = _created()


class OpsUser(Base):
    __tablename__ = "ops_users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ops_organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    # SHA-256 of the bearer token. The token itself is shown once, never stored.
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _created()


class Project(Base):
    __tablename__ = "ops_projects"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ops_organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ops_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="RECRUITMENT")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # PRIVATE: owner only. ORGANIZATION: anyone in the owner's organization.
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="PRIVATE")
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _created()


class Watchlist(Base):
    __tablename__ = "ops_watchlists"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ops_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ops_users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = _created()


class WatchlistItem(Base):
    __tablename__ = "ops_watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "entity_type", "entity_id", name="uq_watchlist_entity"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ops_watchlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(256), nullable=False)
    # {"metric": ..., "operator": ">=", "threshold": ..., "window_matches": N}
    condition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    last_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Alert(Base):
    """An alert exists only with evidence and a dedup key (§25)."""

    __tablename__ = "ops_alerts"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_alert_dedup_key"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ops_organizations.id", ondelete="CASCADE"), index=True
    )
    watchlist_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ops_watchlist_items.id", ondelete="SET NULL")
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    condition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    threshold: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ops_users.id", ondelete="SET NULL"))


class Notification(Base):
    __tablename__ = "ops_notifications"
    __table_args__ = (UniqueConstraint("alert_id", "channel", name="uq_notification_alert_channel"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ops_alerts.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    provider_response: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DecisionRecord(Base):
    """A recorded decision. Immutable (trigger); revisions are new rows."""

    __tablename__ = "ops_decisions"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_decision_idempotency"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ops_projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ops_users.id", ondelete="RESTRICT"), nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ops_decisions.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_graph: Mapped[dict] = mapped_column(JSONB, nullable=False)
    inference_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    data_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _created()


class AuditEvent(Base):
    """Hash-chained, append-only audit trail (trigger-enforced)."""

    __tablename__ = "ops_audit_events"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Incident(Base):
    """Incident lifecycle: DETECT -> ALERT -> ISOLATE -> DEGRADED -> RECOVER -> VERIFY -> AUDIT."""

    __tablename__ = "ops_incidents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_drill: Mapped[bool] = mapped_column(Boolean, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    timeline: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    degraded_behaviour: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class FieldValidationRecord(Base):
    """Telemetry for one executed operational workflow step (§31)."""

    __tablename__ = "ops_field_validation"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workflow: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ops_users.id", ondelete="SET NULL"))
    execution_ms: Mapped[float] = mapped_column(Float, nullable=False)
    data_sufficiency: Mapped[str] = mapped_column(String(32), nullable=False)
    system_response: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = _created()
