"""Phase 17 live operations: persistent operational state, snapshot request
metadata, and database-enforced immutability for predictions, decisions and
the audit trail.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")

IMMUTABLE_TABLES = ("ops_inference_log", "ops_decisions", "ops_audit_events")


def _ts(name: str, nullable: bool = True, default: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=NOW if default else None)


def upgrade() -> None:
    # --- Bronze request metadata (§6) ---
    op.add_column("data_snapshots", _ts("provider_retrieved_at"))
    op.add_column("data_snapshots", sa.Column("http_status", sa.Integer(), nullable=True))
    op.add_column("data_snapshots", sa.Column("content_type", sa.String(128), nullable=True))
    op.add_column("data_snapshots", sa.Column("source_url", sa.String(1024), nullable=True))

    op.create_table(
        "ops_provider_probes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("resource", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.String(512), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("authentication_state", sa.String(32), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("latency_ms", sa.Float()),
        sa.Column("quota", JSONB, nullable=False, server_default="{}"),
        sa.Column("capability", sa.String(64)),
        sa.Column("detail", sa.Text()),
        _ts("probed_at", nullable=False),
    )
    op.create_index("ix_ops_provider_probes_provider", "ops_provider_probes", ["provider"])
    op.create_index("ix_ops_provider_probes_probed_at", "ops_provider_probes", ["probed_at"])

    op.create_table(
        "ops_contract_fingerprints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("resource", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("field_types", JSONB, nullable=False),
        sa.Column("registered_from_snapshot", sa.String(64)),
        _ts("registered_at", nullable=False, default=True),
        sa.UniqueConstraint("provider", "resource", name="uq_contract_provider_resource"),
    )

    op.create_table(
        "ops_job_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("job_name", sa.String(128), nullable=False),
        sa.Column("schedule_class", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(64)),
        sa.Column("resource", sa.String(64)),
        sa.Column("parameters", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        _ts("started_at", nullable=False),
        _ts("finished_at"),
        sa.Column("latency_ms", sa.Float()),
        sa.Column("records", sa.Integer()),
        sa.Column("errors", JSONB, nullable=False, server_default="[]"),
        sa.Column("ingestion_run_id", UUID, sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL")),
        sa.Column("snapshot_sha256", sa.String(64)),
    )
    op.create_index("ix_ops_job_runs_job_name", "ops_job_runs", ["job_name"])
    op.create_index("ix_ops_job_runs_status", "ops_job_runs", ["status"])

    op.create_table(
        "ops_quality_reports",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64)),
        sa.Column("overall", sa.String(8), nullable=False),
        sa.Column("checks", JSONB, nullable=False),
        sa.Column("records_examined", sa.Integer(), nullable=False),
        _ts("created_at", nullable=False, default=True),
    )
    op.create_index("ix_ops_quality_reports_scope", "ops_quality_reports", ["scope"])
    op.create_index("ix_ops_quality_reports_snapshot_sha256", "ops_quality_reports", ["snapshot_sha256"])

    op.create_table(
        "ops_feature_refresh",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("feature", sa.String(128), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("source_dependency", sa.String(256), nullable=False),
        sa.Column("previous_version", sa.String(64)),
        sa.Column("new_version", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("values", JSONB, nullable=False, server_default="{}"),
        _ts("refreshed_at", nullable=False),
    )
    op.create_index("ix_ops_feature_refresh_feature", "ops_feature_refresh", ["feature"])

    op.create_table(
        "ops_model_registry",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("feature_version", sa.String(64), nullable=False),
        sa.Column("dataset_version", sa.String(128), nullable=False),
        _ts("data_cutoff"),
        sa.Column("artifact_sha256", sa.String(64)),
        sa.Column("supported_competitions", JSONB, nullable=False),
        sa.Column("deployment_state", sa.String(32), nullable=False),
        sa.Column("validation_metrics", JSONB, nullable=False),
        sa.Column("min_history_matches", sa.Integer(), nullable=False),
        sa.Column("max_feature_age_hours", sa.Float()),
        _ts("registered_at", nullable=False, default=True),
        sa.UniqueConstraint("model_id", "model_version", name="uq_ops_model_version"),
    )
    op.create_index("ix_ops_model_registry_domain", "ops_model_registry", ["domain"])

    op.create_table(
        "ops_inference_log",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.Column("prediction_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("model_id", sa.String(128)),
        sa.Column("model_version", sa.String(64)),
        sa.Column("feature_version", sa.String(64)),
        sa.Column("dataset_version", sa.String(128)),
        _ts("data_cutoff"),
        sa.Column("competition", sa.String(128)),
        sa.Column("subject_id", sa.String(128)),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("output", JSONB, nullable=False),
        sa.Column("features_used", JSONB, nullable=False),
        sa.Column("missing_features", JSONB, nullable=False),
        sa.Column("reasons", JSONB, nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("is_ood", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("evidence", JSONB, nullable=False),
        _ts("created_at", nullable=False, default=True),
    )
    for col in ("domain", "status", "competition", "subject_id"):
        op.create_index(f"ix_ops_inference_log_{col}", "ops_inference_log", [col])

    op.create_table(
        "ops_outcomes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("inference_id", UUID, sa.ForeignKey("ops_inference_log.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("realized", JSONB, nullable=False),
        sa.Column("outcome_source", sa.String(128), nullable=False),
        sa.Column("outcome_snapshot_sha256", sa.String(64)),
        sa.Column("observation_mode", sa.String(32), nullable=False),
        _ts("observed_at", nullable=False),
        sa.Column("evaluation", JSONB, nullable=False),
        _ts("evaluated_at", nullable=False, default=True),
        sa.UniqueConstraint("inference_id", name="uq_outcome_inference"),
    )

    op.create_table(
        "ops_organizations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        _ts("created_at", nullable=False, default=True),
    )
    op.create_table(
        "ops_users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("ops_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("email", sa.String(256), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("token_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _ts("created_at", nullable=False, default=True),
    )
    op.create_index("ix_ops_users_organization_id", "ops_users", ["organization_id"])

    op.create_table(
        "ops_projects",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("ops_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_user_id", UUID, sa.ForeignKey("ops_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("parameters", JSONB, nullable=False),
        _ts("created_at", nullable=False, default=True),
    )
    op.create_index("ix_ops_projects_organization_id", "ops_projects", ["organization_id"])
    op.create_index("ix_ops_projects_owner_user_id", "ops_projects", ["owner_user_id"])

    op.create_table(
        "ops_watchlists",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("ops_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", UUID, sa.ForeignKey("ops_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        _ts("created_at", nullable=False, default=True),
    )
    op.create_index("ix_ops_watchlists_project_id", "ops_watchlists", ["project_id"])

    op.create_table(
        "ops_watchlist_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("watchlist_id", UUID, sa.ForeignKey("ops_watchlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("entity_name", sa.String(256), nullable=False),
        sa.Column("condition", JSONB, nullable=False),
        sa.Column("last_state", JSONB, nullable=False),
        _ts("last_evaluated_at"),
        _ts("created_at", nullable=False, default=True),
        sa.UniqueConstraint("watchlist_id", "entity_type", "entity_id", name="uq_watchlist_entity"),
    )
    op.create_index("ix_ops_watchlist_items_watchlist_id", "ops_watchlist_items", ["watchlist_id"])

    op.create_table(
        "ops_alerts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dedup_key", sa.String(64), nullable=False),
        sa.Column("organization_id", UUID, sa.ForeignKey("ops_organizations.id", ondelete="CASCADE")),
        sa.Column("watchlist_item_id", UUID, sa.ForeignKey("ops_watchlist_items.id", ondelete="SET NULL")),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("condition", JSONB, nullable=False),
        sa.Column("threshold", JSONB, nullable=False),
        sa.Column("evidence", JSONB, nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        _ts("triggered_at", nullable=False),
        _ts("delivered_at"),
        _ts("acknowledged_at"),
        _ts("resolved_at"),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("ops_users.id", ondelete="SET NULL")),
        sa.UniqueConstraint("dedup_key", name="uq_alert_dedup_key"),
        # §25: an alert without evidence is not an alert.
        sa.CheckConstraint("jsonb_typeof(evidence) = 'array' AND jsonb_array_length(evidence) > 0",
                           name="ck_alert_has_evidence"),
    )
    for col in ("organization_id", "category", "state"):
        op.create_index(f"ix_ops_alerts_{col}", "ops_alerts", [col])

    op.create_table(
        "ops_notifications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("alert_id", UUID, sa.ForeignKey("ops_alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("provider_response", sa.Text()),
        _ts("created_at", nullable=False, default=True),
        _ts("updated_at", nullable=False, default=True),
        sa.UniqueConstraint("alert_id", "channel", name="uq_notification_alert_channel"),
    )
    op.create_index("ix_ops_notifications_state", "ops_notifications", ["state"])

    op.create_table(
        "ops_decisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("ops_projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("ops_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supersedes_id", UUID, sa.ForeignKey("ops_decisions.id", ondelete="RESTRICT")),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("decision", sa.String(64), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_graph", JSONB, nullable=False),
        sa.Column("inference_ids", JSONB, nullable=False),
        _ts("data_cutoff", nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        _ts("created_at", nullable=False, default=True),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_decision_idempotency"),
    )
    op.create_index("ix_ops_decisions_project_id", "ops_decisions", ["project_id"])

    op.create_table(
        "ops_audit_events",
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("resource", sa.String(256), nullable=False),
        sa.Column("details", JSONB, nullable=False),
        sa.Column("correlation_id", sa.String(64)),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False, unique=True),
        _ts("created_at", nullable=False),
    )
    op.create_index("ix_ops_audit_events_event_type", "ops_audit_events", ["event_type"])

    op.create_table(
        "ops_incidents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("is_drill", sa.Boolean(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("timeline", JSONB, nullable=False),
        sa.Column("degraded_behaviour", sa.Text()),
        _ts("detected_at", nullable=False),
        _ts("recovered_at"),
        sa.Column("verification", JSONB, nullable=False),
    )
    op.create_index("ix_ops_incidents_kind", "ops_incidents", ["kind"])

    op.create_table(
        "ops_field_validation",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workflow", sa.String(64), nullable=False),
        sa.Column("step", sa.String(64), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("ops_users.id", ondelete="SET NULL")),
        sa.Column("execution_ms", sa.Float(), nullable=False),
        sa.Column("data_sufficiency", sa.String(32), nullable=False),
        sa.Column("system_response", sa.String(64), nullable=False),
        sa.Column("evidence_available", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("outcome", sa.String(32), nullable=False),
        _ts("created_at", nullable=False, default=True),
    )
    op.create_index("ix_ops_field_validation_workflow", "ops_field_validation", ["workflow"])

    # --- Append-only enforcement (§15, §20, §43, adversarial 12/13/29) ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ops_reject_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'IMMUTABLE_RECORD: % on % is not permitted', TG_OP, TG_TABLE_NAME
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION ops_reject_mutation();"
        )


def downgrade() -> None:
    # Dropping evidence tables destroys immutable history. The downgrade
    # exists for development databases only; see docs/PHASE_17_DISASTER_RECOVERY.md.
    for table in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table};")
    op.execute("DROP FUNCTION IF EXISTS ops_reject_mutation();")
    for table in (
        "ops_field_validation", "ops_incidents", "ops_audit_events", "ops_decisions",
        "ops_notifications", "ops_alerts", "ops_watchlist_items", "ops_watchlists",
        "ops_projects", "ops_users", "ops_organizations", "ops_outcomes",
        "ops_inference_log", "ops_model_registry", "ops_feature_refresh",
        "ops_quality_reports", "ops_job_runs", "ops_contract_fingerprints",
        "ops_provider_probes",
    ):
        op.drop_table(table)
    for col in ("source_url", "content_type", "http_status", "provider_retrieved_at"):
        op.drop_column("data_snapshots", col)
