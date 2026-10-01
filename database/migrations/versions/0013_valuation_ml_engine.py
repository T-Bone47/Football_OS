"""valuation ML engine models and predictions (Phase 4.2W)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. valuation_models
    op.create_table(
        "valuation_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False, server_default="VALUATION_ML_V1"),
        sa.Column("dataset_version", sa.String(32), nullable=False),
        sa.Column("feature_set_version", sa.String(32), nullable=False),
        sa.Column("algorithm", sa.String(64), nullable=False),
        sa.Column("training_start_date", sa.Date(), nullable=True),
        sa.Column("training_end_date", sa.Date(), nullable=True),
        sa.Column("test_start_date", sa.Date(), nullable=True),
        sa.Column("test_end_date", sa.Date(), nullable=True),
        sa.Column("hyperparameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("release_checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="MODEL_VALIDATED"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("artifact_path", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("model_id", name="uq_valuation_model_id"),
    )
    op.create_index("ix_valuation_models_status", "valuation_models", ["status"])
    op.create_index("ix_valuation_models_is_active", "valuation_models", ["is_active"])

    # 2. valuation_predictions
    op.create_table(
        "valuation_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("estimated_value_eur", sa.Float(), nullable=False),
        sa.Column("lower_bound_eur", sa.Float(), nullable=False),
        sa.Column("upper_bound_eur", sa.Float(), nullable=False),
        sa.Column("uncertainty_eur", sa.Float(), nullable=False),
        sa.Column("coverage_level", sa.Float(), nullable=False, server_default="0.80"),
        sa.Column("data_status", sa.String(32), nullable=False, server_default="VALUATION_AVAILABLE"),
        sa.Column("feature_version", sa.String(32), nullable=False),
        sa.Column("top_features", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("gate_decision", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_val_pred_player_as_of", "valuation_predictions", ["player_id", "as_of"])
    op.create_index("ix_val_pred_model_version", "valuation_predictions", ["model_version"])
    op.create_index("ix_val_pred_data_status", "valuation_predictions", ["data_status"])


def downgrade() -> None:
    op.drop_table("valuation_predictions")
    op.drop_table("valuation_models")
