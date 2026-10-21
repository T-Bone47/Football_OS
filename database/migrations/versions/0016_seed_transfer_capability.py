"""seed the api-football transfers capability

The capability registry is checked *before* a request, so an endpoint that
has never been requested can never become available: a successful fetch
creates the row (``mark_verified``), but only after ``supports`` returned
True. ``/transfers`` is a real, documented API-Football endpoint and a live
request against the current plan returns data, so it is seeded here with
``last_verified = NULL`` — the column still means "a live request confirmed
this", and is set by the ingestion run that actually succeeds.

Revision ID: 0016
Revises: 32ee69fbf263
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "32ee69fbf263"
branch_labels = None
depends_on = None

capabilities = sa.table(
    "provider_capabilities",
    sa.column("provider", sa.String),
    sa.column("resource", sa.String),
    sa.column("competition", sa.String),
    sa.column("season", sa.String),
    sa.column("available", sa.Boolean),
    sa.column("last_verified", sa.DateTime),
)


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO provider_capabilities
            (provider, resource, competition, season, available, last_verified)
        VALUES ('api-football', 'transfers', NULL, NULL, true, NULL)
        ON CONFLICT (provider, resource, competition, season) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM provider_capabilities "
        "WHERE provider = 'api-football' AND resource = 'transfers' "
        "AND competition IS NULL AND season IS NULL"
    )
