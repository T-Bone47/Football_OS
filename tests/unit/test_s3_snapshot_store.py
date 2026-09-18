"""Unit-tests S3SnapshotStore's logic against a MOCKED S3 (moto) — this is
NOT a test against a real MinIO/S3 endpoint. See
docs/DEVELOPMENT_STATUS.md for what that distinction means here.
"""
from datetime import datetime, timezone

import boto3
import pytest
from moto import mock_aws

from app.ingestion.s3_snapshot_store import S3SnapshotStore
from app.providers.base import RawResponse


@pytest.fixture
def bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="football-os-bronze")
        yield "football-os-bronze"


async def test_save_is_content_addressed_and_idempotent(bucket):
    store = S3SnapshotStore(bucket=bucket, region="us-east-1")
    response = RawResponse(
        content=b'{"hello": "world"}',
        content_type="application/json",
        source_url="https://example.test/x",
        retrieved_at=datetime.now(timezone.utc),
        status_code=200,
    )

    digest_1, loc_1 = await store.save("statsbomb", "competitions", response)
    digest_2, loc_2 = await store.save("statsbomb", "competitions", response)

    assert digest_1 == digest_2
    assert loc_1 == loc_2
    assert loc_1 == f"s3://{bucket}/bronze/statsbomb/competitions/{digest_1}.json"


async def test_different_content_yields_different_key(bucket):
    store = S3SnapshotStore(bucket=bucket, region="us-east-1")
    now = datetime.now(timezone.utc)
    r1 = RawResponse(b"a", "application/json", "https://x", now, 200)
    r2 = RawResponse(b"b", "application/json", "https://x", now, 200)

    _, loc1 = await store.save("statsbomb", "competitions", r1)
    _, loc2 = await store.save("statsbomb", "competitions", r2)

    assert loc1 != loc2
