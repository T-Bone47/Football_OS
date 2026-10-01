"""Pydantic schemas for Canonical Action API (Phase 3.1)."""
from __future__ import annotations

import datetime
import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict


class CanonicalActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_id: uuid.UUID
    player_id: uuid.UUID
    club_id: uuid.UUID
    period: int | None = None
    minute: int
    extra_minute: int | None = None
    action_type: str
    action_subtype: str
    action_quantity: int
    outcome: str
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    recipient_player_id: uuid.UUID | None = None
    related_player_id: uuid.UUID | None = None
    provider: str
    provider_event_id: str | None = None
    normalization_version: str
    raw_data: dict[str, Any]
    created_at: datetime.datetime


class PlayerActionsResponse(BaseModel):
    player_id: uuid.UUID
    total_actions: int
    limit: int
    offset: int
    actions: list[CanonicalActionResponse]
