"""Authentication: token expiry, revocation and OIDC subject binding (Phase 18, R9).

Revision ID: 0017
Revises: 0016

Existing tokens get no expiry (NULL), so nothing is silently invalidated by
the migration. New tokens are issued with an expiry (TOKEN_TTL_HOURS).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ops_users", sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ops_users", sa.Column("token_revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ops_users", sa.Column("oidc_issuer", sa.String(512), nullable=True))
    op.add_column("ops_users", sa.Column("oidc_subject", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_ops_user_oidc_subject", "ops_users", ["oidc_issuer", "oidc_subject"])


def downgrade() -> None:
    op.drop_constraint("uq_ops_user_oidc_subject", "ops_users", type_="unique")
    for col in ("oidc_subject", "oidc_issuer", "token_revoked_at", "token_expires_at"):
        op.drop_column("ops_users", col)
