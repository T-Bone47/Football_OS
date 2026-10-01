"""Persisted decision analyses (Phase 18, R12/R22).

Revision ID: 0021
Revises: 0020

Recruitment, replacement, scenario and comparison analyses were cached in a
process-wide dict (lost on restart, visible across organizations). They are
now rows scoped to an organization, with the served payload's SHA-256.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_decision_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_type", sa.String(32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["ops_organizations.id"], ondelete="RESTRICT",
                                name="fk_ops_decision_analyses_organization_id"),
        sa.ForeignKeyConstraint(["user_id"], ["ops_users.id"], ondelete="RESTRICT",
                                name="fk_ops_decision_analyses_user_id"),
        sa.UniqueConstraint("organization_id", "decision_id", "content_sha256", name="uq_decision_analysis_content"),
    )
    op.create_index("ix_ops_decision_analyses_organization_id", "ops_decision_analyses", ["organization_id"])
    op.create_index("ix_ops_decision_analyses_decision_id", "ops_decision_analyses", ["decision_id"])


def downgrade() -> None:
    op.drop_index("ix_ops_decision_analyses_decision_id", table_name="ops_decision_analyses")
    op.drop_index("ix_ops_decision_analyses_organization_id", table_name="ops_decision_analyses")
    op.drop_table("ops_decision_analyses")
