from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base. Every canonical entity (Phase 1+) and every
    provenance table (Phase 0) registers on this metadata so a single
    Alembic target_metadata sees the whole schema."""
