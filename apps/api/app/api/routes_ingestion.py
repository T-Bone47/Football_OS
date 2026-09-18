"""Ingestion endpoints (architecture doc §32/§33/§47)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.provenance import IngestionRun
from app.db.session import get_session
from app.ingestion.capability_registry import CapabilityRegistry
from app.ingestion.factory import build_snapshot_store
from app.ingestion.service import IngestionService
from app.providers.registry import default_registry

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


class CreateIngestionRunRequest(BaseModel):
    provider: str
    resource: str
    params: dict = {}


class IngestionRunResponse(BaseModel):
    run_id: uuid.UUID
    provider: str
    resource: str
    status: str
    record_count: int | None = None
    error: str | None = None

    @classmethod
    def from_run(cls, run: IngestionRun, provider: str) -> "IngestionRunResponse":
        return cls(
            run_id=run.id,
            provider=provider,
            resource=run.endpoint,
            status=run.status.value if hasattr(run.status, "value") else run.status,
            record_count=run.record_count,
            error=run.error,
        )


@router.post("/runs", response_model=IngestionRunResponse)
async def create_ingestion_run(
    body: CreateIngestionRunRequest, session: AsyncSession = Depends(get_session)
) -> IngestionRunResponse:
    settings = get_settings()
    service = IngestionService(
        session=session,
        provider_registry=default_registry,
        snapshot_store=build_snapshot_store(settings),
        capability_registry=CapabilityRegistry(session),
    )
    run = await service.run(body.provider, body.resource, **body.params)
    return IngestionRunResponse.from_run(run, body.provider)


@router.get("/runs/{run_id}", response_model=IngestionRunResponse)
async def get_ingestion_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> IngestionRunResponse:
    run = (
        await session.execute(
            select(IngestionRun).where(IngestionRun.id == run_id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="ingestion run not found")
    await session.refresh(run, attribute_names=["data_source"])
    return IngestionRunResponse.from_run(run, run.data_source.name)
