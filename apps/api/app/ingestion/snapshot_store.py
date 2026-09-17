"""Content-addressed raw storage (architecture doc §13). Layout matches the
spec exactly: bronze/<provider>/<resource>/<sha256>.json — so swapping the
backend for S3/MinIO (ADR-001) later means adding one class, not touching
callers.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from app.providers.base import RawResponse


class SnapshotStore(Protocol):
    async def save(self, provider: str, resource: str, response: RawResponse) -> tuple[str, str]:
        """Persist raw bytes. Returns (sha256, storage_location)."""
        ...


class LocalFilesystemSnapshotStore:
    """Phase-0 backend. ponytail: synchronous file I/O inside an async method
    is a real blocking call — fine at today's volume (single adapter, test
    traffic), not fine once ingestion runs concurrently at scale. Upgrade
    path: swap for the S3/MinIO implementation from ADR-001, which is async
    natively; this class's callers don't change.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    async def save(self, provider: str, resource: str, response: RawResponse) -> tuple[str, str]:
        digest = hashlib.sha256(response.content).hexdigest()
        target_dir = self._root / provider / resource
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{digest}.json"
        if not target_path.exists():
            target_path.write_bytes(response.content)
        return digest, str(target_path)
