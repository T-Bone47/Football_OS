"""Query interface over the ProviderCapability table (architecture doc §22).
Ingestion asks this before requesting; it never asks the adapter directly."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.capability import ProviderCapability


class CapabilityRegistry:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def supports(
        self, provider: str, resource: str, competition: str | None = None, season: str | None = None
    ) -> bool:
        stmt = select(ProviderCapability).where(
            ProviderCapability.provider == provider,
            ProviderCapability.resource == resource,
            ProviderCapability.competition == competition,
            ProviderCapability.season == season,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return bool(row and row.available)

    async def mark_verified(
        self, provider: str, resource: str, competition: str | None = None, season: str | None = None
    ) -> None:
        """Called after a real successful fetch — this is the only path that
        sets last_verified, so that column always means 'a live request
        actually confirmed this', not 'we assumed it'."""
        stmt = select(ProviderCapability).where(
            ProviderCapability.provider == provider,
            ProviderCapability.resource == resource,
            ProviderCapability.competition == competition,
            ProviderCapability.season == season,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ProviderCapability(
                provider=provider, resource=resource, competition=competition, season=season
            )
            self._session.add(row)
        row.available = True
        row.last_verified = datetime.now(timezone.utc)
        await self._session.flush()
