"""Provider-independent contract (architecture doc §11). Nothing above this
layer is allowed to know which provider produced a RawResponse — adapters
translate provider-specific HTTP/auth/pagination into this one shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class RawResponse:
    content: bytes
    content_type: str
    source_url: str
    retrieved_at: datetime
    status_code: int


class FootballDataProvider(Protocol):
    name: str

    async def fetch(self, resource: str, **params: Any) -> RawResponse: ...

    async def close(self) -> None: ...
