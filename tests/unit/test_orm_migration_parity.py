"""Static ORM <-> migration parity (R19). No SQLAlchemy needed: both sides are parsed with `ast`.

The checker must flag every kind of drift, apply migrations in revision order, and refuse to pass
silently over anything it cannot parse.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_orm_migration_parity", ROOT / "tools" / "check_orm_migration_parity.py")
parity = importlib.util.module_from_spec(_spec)
sys.modules["check_orm_migration_parity"] = parity
_spec.loader.exec_module(parity)

ORM = '''
class Club(Base):
    __tablename__ = "clubs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    country: Mapped[str | None] = mapped_column(String(64), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"))
'''
MIG = '''
revision = "0001"
down_revision = None

def upgrade():
    op.create_table(
        "clubs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("owners.id"), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_clubs_country", "clubs", ["country"])
'''
OWNERS_ORM = '''
class Owner(Base):
    __tablename__ = "owners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
'''
OWNERS_MIG = '''
revision = "0000"
down_revision = None

def upgrade():
    op.create_table("owners", sa.Column("id", sa.Integer(), primary_key=True))
'''


def _check(orm_sources, mig_sources):
    orm = parity.parse_orm_sources(orm_sources)
    mig = parity.parse_migration_sources(mig_sources)
    return parity.compare(orm, mig)


def _chain(*migs):
    """OWNERS first, then the given migrations chained in order."""
    return [("0000_owners.py", OWNERS_MIG)] + [(f"{i + 1:04d}.py", m) for i, m in enumerate(migs)]


def _mig1(extra_down="0000"):
    return MIG.replace('down_revision = None', f'down_revision = "{extra_down}"')


def kinds(findings, severity="DRIFT"):
    return sorted({f.kind for f in findings if f.severity == severity})


def test_identical_schema_has_no_drift():
    assert kinds(_check([ORM, OWNERS_ORM], _chain(_mig1()))) == []


def test_table_missing_from_migrations_and_from_orm():
    assert "TABLE_MISSING_IN_MIGRATIONS" in kinds(_check([ORM, OWNERS_ORM], [("0000_owners.py", OWNERS_MIG)]))
    assert "TABLE_MISSING_IN_ORM" in kinds(_check([OWNERS_ORM], _chain(_mig1())))


def test_column_missing_on_either_side():
    orm_extra = ORM + '    rating: Mapped[float | None] = mapped_column(Float)\n'
    assert "COLUMN_MISSING_IN_MIGRATIONS" in kinds(_check([orm_extra, OWNERS_ORM], _chain(_mig1())))
    mig_extra = _mig1().replace('sa.UniqueConstraint("name"),', 'sa.Column("rating", sa.Float()),\n        sa.UniqueConstraint("name"),')
    assert "COLUMN_MISSING_IN_ORM" in kinds(_check([ORM, OWNERS_ORM], _chain(mig_extra)))


def test_nullability_mismatch_is_drift():
    orm = ORM.replace("Mapped[str | None] = mapped_column(String(64), index=True)", "Mapped[str] = mapped_column(String(64), index=True)")
    assert "NULLABLE_MISMATCH" in kinds(_check([orm, OWNERS_ORM], _chain(_mig1())))


def test_type_and_length_mismatch_are_drift():
    t = _mig1().replace('sa.Column("country", sa.String(64), nullable=True)', 'sa.Column("country", sa.Integer(), nullable=True)')
    assert "TYPE_MISMATCH" in kinds(_check([ORM, OWNERS_ORM], _chain(t)))
    l = _mig1().replace('sa.Column("country", sa.String(64), nullable=True)', 'sa.Column("country", sa.String(128), nullable=True)')
    assert "LENGTH_MISMATCH" in kinds(_check([ORM, OWNERS_ORM], _chain(l)))


def test_foreign_key_unique_and_index_mismatches_are_drift():
    no_fk = _mig1().replace('sa.ForeignKey("owners.id"), ', "")
    assert "FK_MISMATCH" in kinds(_check([ORM, OWNERS_ORM], _chain(no_fk)))
    no_unique = _mig1().replace('        sa.UniqueConstraint("name"),\n', "")
    assert "UNIQUE_MISMATCH" in kinds(_check([ORM, OWNERS_ORM], _chain(no_unique)))
    no_index = _mig1().replace('    op.create_index("ix_clubs_country", "clubs", ["country"])\n', "")
    assert "INDEX_MISMATCH" in kinds(_check([ORM, OWNERS_ORM], _chain(no_index)))


def test_migrations_are_applied_in_revision_order_not_file_order():
    add = 'revision = "0002"\ndown_revision = "0001"\n\ndef upgrade():\n    op.add_column("clubs", sa.Column("rating", sa.Float(), nullable=True))\n    op.alter_column("clubs", "country", nullable=False)\n'
    orm = ORM.replace("Mapped[str | None] = mapped_column(String(64), index=True)", "Mapped[str] = mapped_column(String(64), index=True)")
    orm += '    rating: Mapped[float | None] = mapped_column(Float)\n'
    shuffled = [("zzz_second.py", add), ("aaa_first.py", _mig1()), ("0000_owners.py", OWNERS_MIG)]  # file order is wrong on purpose
    assert kinds(_check([orm, OWNERS_ORM], shuffled)) == []


def test_drop_column_and_drop_table_are_applied():
    drop = 'revision = "0002"\ndown_revision = "0001"\n\ndef upgrade():\n    op.drop_column("clubs", "country")\n'
    orm = ORM.replace('    country: Mapped[str | None] = mapped_column(String(64), index=True)\n', "")
    mig = [("0000.py", OWNERS_MIG), ("0001.py", _mig1()), ("0002.py", drop.replace("op.drop_column", "op.drop_index('ix_clubs_country', table_name='clubs')\n    op.drop_column"))]
    assert kinds(_check([orm, OWNERS_ORM], mig)) == []


def test_operations_it_cannot_parse_are_reported_not_ignored():
    odd = 'revision = "0002"\ndown_revision = "0001"\n\ndef upgrade():\n    op.rename_table("clubs", "teams")\n    op.execute("ALTER TABLE clubs ADD CONSTRAINT x CHECK (id > 0)")\n'
    findings = _check([ORM, OWNERS_ORM], [("0000.py", OWNERS_MIG), ("0001.py", _mig1()), ("0002.py", odd)])
    assert {"UNPARSED_OPERATION"} <= set(kinds(findings, "WARN"))


def test_helper_built_tables_are_flagged_partial_and_not_compared_column_by_column():
    helper = 'revision = "0001"\ndown_revision = "0000"\n\ndef upgrade():\n    op.create_table("clubs", *_cols())\n'
    findings = _check([ORM, OWNERS_ORM], _chain(helper))
    assert "PARTIAL_PARSE" in kinds(findings, "WARN")
    assert not [f for f in findings if f.severity == "DRIFT" and f.table == "clubs"]


def test_orm_without_tablename_and_relationships_are_ignored():
    orm = 'class Mixin:\n    created: Mapped[int] = mapped_column(Integer)\n\nclass Club(Base):\n    __tablename__ = "clubs"\n    id: Mapped[int] = mapped_column(Integer, primary_key=True)\n    owner: Mapped["Owner"] = relationship()\n'
    assert set(parity.parse_orm_sources([orm])) == {"clubs"}
    assert set(parity.parse_orm_sources([orm])["clubs"].columns) == {"id"}


def test_repository_orm_matches_its_migrations():
    """The real models vs the real migrations 0001..latest: any drift fails (fix by migration, never by editing this test)."""
    findings = parity.check_repo(ROOT)
    drift = [f for f in findings if f.severity == "DRIFT"]
    assert not drift, "\n".join(f"{f.kind} {f.table}.{f.column or '*'}: {f.detail}" for f in drift[:25])
