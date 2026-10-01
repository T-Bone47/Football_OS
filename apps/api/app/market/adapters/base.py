"""Base interface for Transfer Data Source Adapters (Phase 4.1B).
Enforces pure transformation from provider-specific envelopes into NormalizedTransfer entities.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.market.schemas import NormalizedTransfer


class TransferSourceAdapter(ABC):
    """Abstract base adapter for transfer market data sources."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the source provider (e.g. 'api-football', 'open-transfer-archive')."""
        pass

    @property
    @abstractmethod
    def license_type(self) -> str:
        """Licensing status (e.g. 'Commercial API', 'CC0-1.0', 'CC BY 4.0')."""
        pass

    @abstractmethod
    def transform(self, payload: dict[str, Any] | list[dict[str, Any]]) -> list[NormalizedTransfer]:
        """Pure transformation of raw provider payload into typed NormalizedTransfer models."""
        pass
