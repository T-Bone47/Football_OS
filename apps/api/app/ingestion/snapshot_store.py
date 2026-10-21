"""Content-addressed raw storage (architecture doc §13). Layout matches the
spec exactly: bronze/<provider>/<resource>/<sha256>.json — so swapping the
backend for S3/MinIO (ADR-001) later means adding one class, not touching
callers.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol

from app.providers.base import RawResponse


_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def safe_segment(value: str, label: str) -> str:
    """provider/resource become directory names; reject anything that could leave the bronze root."""
    if not isinstance(value, str) or not _SEGMENT.fullmatch(value) or ".." in value:
        raise ValueError(f"unsafe {label} for a storage path: {value!r}")
    return value


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
        # Sanitize resource for filesystem: replace path separators with underscore
        safe_resource = resource.replace("/", "_").replace("\\", "_")
        target_dir = self._root / safe_segment(provider, "provider") / safe_segment(safe_resource, "resource")
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{digest}.json"
        if not target_path.exists():
            target_path.write_bytes(response.content)
        return digest, str(target_path)
