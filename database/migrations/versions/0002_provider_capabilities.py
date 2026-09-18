"""provider capability registry, seeded from what the architecture doc
already asserts each provider covers (§7 for API-Football, §8 for
football-data.org, §9 + the real StatsBomb test for StatsBomb) — seeding
"available" from the spec's own claims, not fabricating new ones.
StatsBomb "competitions" gets a real last_verified timestamp because a live
request actually confirmed it in this repo's tests; everything else is
available=True/last_verified=NULL until something actually calls it.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
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

# (provider, resource, available, verified)
_SEED = [
    ("statsbomb", "competitions", True, True),   # real live test in this repo
    ("statsbomb", "matches", True, False),
    ("statsbomb", "events", True, False),
    ("statsbomb", "lineups", True, False),
    ("statsbomb", "360", False, False),          # only select competitions — arch doc §25 example
    ("api-football", "leagues", True, False),
    ("api-football", "teams", True, False),
    ("api-football", "players", True, False),
    ("api-football", "fixtures", True, False),
    ("api-football", "standings", True, False),
    ("api-football", "injuries", True, False),
    ("api-football", "predictions", True, False),
    ("football-data-org", "competitions", True, False),
    ("football-data-org", "teams", True, False),
    ("football-data-org", "matches", True, False),
    ("football-data-org", "standings", True, False),
    ("football-data-org", "persons", True, False),
]


def upgrade() -> None:
    op.create_table(
        "provider_capabilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("resource", sa.String(64), nullable=False),
        sa.Column("competition", sa.String(128)),
        sa.Column("season", sa.String(16)),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_verified", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("provider", "resource", "competition", "season", name="uq_capability"),
    )

    now = sa.func.now()
    op.bulk_insert(
        capabilities,
        [
            {
                "provider": p,
                "resource": r,
                "competition": None,
                "season": None,
                "available": avail,
                "last_verified": None,  # set below for the one real-verified row
            }
            for p, r, avail, verified in _SEED
        ],
    )
    # Real timestamp for the one row a live request actually confirmed.
    op.execute(
        "UPDATE provider_capabilities SET last_verified = now() "
        "WHERE provider = 'statsbomb' AND resource = 'competitions'"
    )


def downgrade() -> None:
    op.drop_table("provider_capabilities")
