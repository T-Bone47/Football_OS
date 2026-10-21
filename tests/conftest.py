import os
from pathlib import Path

from dotenv import load_dotenv
import pytest

load_dotenv()
# Real token verification stays ON in tests; the secret just has to exist and be >= 32 bytes.
os.environ.setdefault("AUTH_JWT_SECRET", "test-only-secret-" + "k" * 32)
# Phase 13/14 existing tests exercise the built-in demonstration fixtures, which exist only in demo mode.
os.environ.setdefault("FOOTBALL_OS_DEMO_DATA", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]


def _migrated_schema_present(engine) -> bool:
    """True when the disposable test database still has the migrated schema.

    Several legacy integration suites still call ``Base.metadata.drop_all`` in
    their teardown. Because they share one disposable database, that teardown
    removed the migrated tables (``operational_records``, ``ledger_entries``,
    ``club_identities``, ...) and every suite that ran afterwards failed with
    ``UndefinedTableError``. The leftover ``alembic_version`` row also made
    ``alembic upgrade head`` a no-op on a database whose tables were gone.
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        return bool(
            conn.execute(
                text(
                    "SELECT to_regclass('public.club_identities') IS NOT NULL "
                    "AND to_regclass('public.operational_records') IS NOT NULL "
                    "AND to_regclass('public.ledger_entries') IS NOT NULL"
                )
            ).scalar()
        )


def _restore_migrated_schema(postgres_url: str) -> None:
    """Rebuild the disposable test database from the migration history."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    from sqlalchemy.orm import declarative_base

    from app.db.base import Base
    import app.db.models  # noqa: F401 - registers every ORM table on Base.metadata
    from app.db.urls import to_sync_url

    sync_url = to_sync_url(postgres_url)

    # Remove whatever is left (the destructive suites drop ORM tables) so the
    # migration history can rebuild the schema cleanly.
    engine = create_engine(sync_url)
    try:
        Base.metadata.drop_all(engine, checkfirst=True)
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    finally:
        engine.dispose()

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = postgres_url
    try:
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "database" / "migrations"))
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture(scope="session")
def _schema_guard_engine(postgres_url):
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from app.db.urls import to_sync_url

    engine = create_engine(to_sync_url(postgres_url), poolclass=NullPool)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _migrated_schema_guard(postgres_url, _schema_guard_engine):
    """Keep the shared disposable test database usable for every test.

    This is a safety net, not a licence to drop tables: the destructive
    fixtures should be migrated to transaction rollback (see
    docs/KNOWN_LIMITATIONS.md, L9). Until then, a suite that removes the
    schema can no longer break the suites that follow it.
    """
    if not _migrated_schema_present(_schema_guard_engine):
        _restore_migrated_schema(postgres_url)
    yield



@pytest.fixture(scope="session")
def postgres_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://fios:fios@localhost:5432/fios_test",
    )


@pytest.fixture(autouse=True)
def _functional_tests_run_as_authenticated_admin(request):
    """Functional API tests are not about authentication, so they run as an authenticated org admin via
    FastAPI's dependency override. Tests that exercise authentication itself carry @pytest.mark.real_auth
    and run with NO override (they mint real tokens with tests/auth_helpers.py)."""
    if request.node.get_closest_marker("real_auth"):
        yield
        return
    try:
        from app.main import app
        from app.security.deps import get_principal
        from app.security.tokens import Principal
    except Exception:  # pure unit tests in an environment without the web stack
        yield
        return
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="test_admin", roles=frozenset({"admin"}), org_id="org_test", email="admin@test.invalid"
    )
    yield
    app.dependency_overrides.pop(get_principal, None)
