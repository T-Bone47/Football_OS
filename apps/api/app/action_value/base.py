"""Action-Value Foundation interfaces and data contracts (Phase 3.1I/J).
Defines abstract models, data sufficiency gates, and evaluation contracts.
"""
from __future__ import annotations

import abc
import datetime
import uuid
from typing import Any
from pydantic import BaseModel


class ActionValueItem(BaseModel):
    action_id: uuid.UUID
    action_type: str
    action_subtype: str
    minute: int
    raw_value: float | None = None
    spatial_x: float | None = None
    spatial_y: float | None = None
    impact_score: float | None = None
    outcome: str


class ActionValueResult(BaseModel):
    player_id: uuid.UUID
    model_name: str
    model_version: str
    status: str  # EVALUATED, INSUFFICIENT_DATA, INSUFFICIENT_SAMPLE
    spatial_data_sufficient: bool
    total_actions_evaluated: int
    net_action_value: float | None = None
    action_value_per_90: float | None = None
    data_limitation_reason: str | None = None
    licensing_requirements: list[str] = []
    actions_sample: list[ActionValueItem] = []
    evaluation_metadata: dict[str, Any] = {}
    evaluated_at: datetime.datetime


class ActionValueModel(abc.ABC):
    """Abstract interface for Action-Value and Threat models."""

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        pass

    @property
    @abc.abstractmethod
    def model_version(self) -> str:
        pass

    @abc.abstractmethod
    def evaluate(
        self,
        player_id: uuid.UUID,
        actions: list[Any],
        minutes: int,
    ) -> ActionValueResult:
        """Evaluates action value for a player over a sequence of canonical actions."""
        pass
