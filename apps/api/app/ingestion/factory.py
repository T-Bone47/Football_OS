"""Builds the SnapshotStore the app should use, based on settings — the one
place that knows about both backends so nothing else has to branch on
SNAPSHOT_STORAGE_BACKEND (architecture doc §15).
"""
from __future__ import annotations

from app.config import Settings
from app.ingestion.s3_snapshot_store import S3SnapshotStore
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore, SnapshotStore


def build_snapshot_store(settings: Settings) -> SnapshotStore:
    if settings.snapshot_storage_backend == "s3":
        if not settings.s3_bucket:
            raise RuntimeError("SNAPSHOT_STORAGE_BACKEND=s3 requires S3_BUCKET to be set")
        return S3SnapshotStore(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
        )
    return LocalFilesystemSnapshotStore(settings.snapshot_storage_path)
