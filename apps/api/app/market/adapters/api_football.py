"""API-Football Transfer Adapter (Phase 4.1B).
Wraps API-Football envelope parsing into the unified TransferSourceAdapter protocol.
"""
from __future__ import annotations

from typing import Any

from app.market.adapters.base import TransferSourceAdapter
from app.market.normalizer import transform_api_football_transfers
from app.market.schemas import NormalizedTransfer


class ApiFootballTransferAdapter(TransferSourceAdapter):
    """Adapter for official API-Football /transfers responses."""

    @property
    def provider_name(self) -> str:
        return "api-football"

    @property
    def license_type(self) -> str:
        return "Commercial API (API-Sports subscription terms)"

    def transform(self, payload: dict[str, Any] | list[dict[str, Any]]) -> list[NormalizedTransfer]:
        if not isinstance(payload, dict):
            return []
        return transform_api_football_transfers(payload)
