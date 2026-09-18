"""S3-compatible backend for SnapshotStore (architecture doc §15/ADR-001
upgrade path). Same content-addressed key layout as the local backend:
bronze/<provider>/<resource>/<sha256>.json — so callers never know which
backend they're talking to.

Verification status: unit-tested against a mocked S3 (moto) — see
tests/unit/test_s3_snapshot_store.py. NOT tested against a real MinIO/S3
endpoint; this sandbox can't run one. That's a real gap, not a hidden one —
see docs/DEVELOPMENT_STATUS.md.

boto3 is synchronous. Rather than pretend otherwise, calls run in a thread
via asyncio.to_thread — genuinely non-blocking for the event loop, unlike
the local backend's direct sync I/O (see ADR-005).
"""
from __future__ import annotations

import asyncio
import hashlib

import boto3
from botocore.exceptions import ClientError

from app.providers.base import RawResponse


class S3SnapshotStore:
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    async def save(self, provider: str, resource: str, response: RawResponse) -> tuple[str, str]:
        digest = hashlib.sha256(response.content).hexdigest()
        key = f"bronze/{provider}/{resource}/{digest}.json"
        exists = await asyncio.to_thread(self._object_exists, key)
        if not exists:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=response.content,
                ContentType=response.content_type,
            )
        return digest, f"s3://{self._bucket}/{key}"

    def _object_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise
