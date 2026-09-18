"""Provider capability registry (architecture doc §7/§21/§22): answers
"can provider X give resource Y for competition/season Z" without scattering
that logic across every adapter. `available` is what the provider documents
or claims; `last_verified` is only set once a real request actually
confirmed it — the two are deliberately different columns so we never
conflate "documented" with "verified" (build brief §55's VERIFIED discipline
applies here too).
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProviderCapability(Base):
    __tablename__ = "provider_capabilities"
    __table_args__ = (
        UniqueConstraint("provider", "resource", "competition", "season", name="uq_capability"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    # NULL competition/season = "generally", not scoped to one
    competition: Mapped[str | None] = mapped_column(String(128))
    season: Mapped[str | None] = mapped_column(String(16))
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_verified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
