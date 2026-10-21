"""provider identity mapping for canonical competitions

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-21

`competitions` is provider-neutral, so the provider's own competition id needs an
explicit mapping table (the same discipline already used for players and clubs).
Without it, a competition-season row can never be linked to the canonical league
and the player normaliser has to invent a placeholder name.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competition_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_competition_id", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("resolution_method", sa.String(length=64), nullable=False, server_default="DIRECT_PROVIDER_ID"),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_competition_id", name="uq_competition_identity_provider_id"
        ),
    )
    op.create_index("ix_competition_identities_competition_id", "competition_identities", ["competition_id"])


def downgrade() -> None:
    op.drop_index("ix_competition_identities_competition_id", table_name="competition_identities")
    op.drop_table("competition_identities")
