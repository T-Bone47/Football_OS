import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from app.db.base import Base  # noqa: E402
from app.db.models import provenance  # noqa: E402,F401  registers tables on Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://fios:fios@localhost:5432/fios")
    # Name the sync driver explicitly: SQLAlchemy >= 2.1 resolves a bare
    # "postgresql://" to psycopg (v3), but requirements.txt ships psycopg2.
    return url.replace("+asyncpg", "+psycopg2")


def run_migrations_offline() -> None:
    context.configure(url=_sync_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _sync_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # compare_type: column type changes count as drift too (R19).
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
