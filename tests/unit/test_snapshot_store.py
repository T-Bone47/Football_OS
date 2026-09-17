from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.providers.base import RawResponse


async def test_save_is_content_addressed_and_idempotent(tmp_path: Path):
    store = LocalFilesystemSnapshotStore(tmp_path)
    response = RawResponse(
        content=b'{"hello": "world"}',
        content_type="application/json",
        source_url="https://example.test/x",
        retrieved_at=datetime.now(timezone.utc),
        status_code=200,
    )

    digest_1, path_1 = await store.save("statsbomb", "competitions", response)
    digest_2, path_2 = await store.save("statsbomb", "competitions", response)

    assert digest_1 == digest_2
    assert path_1 == path_2
    assert Path(path_1).read_bytes() == response.content
    assert Path(path_1).parent.name == "competitions"
    assert Path(path_1).parent.parent.name == "statsbomb"


async def test_different_content_yields_different_digest(tmp_path: Path):
    store = LocalFilesystemSnapshotStore(tmp_path)
    now = datetime.now(timezone.utc)
    r1 = RawResponse(b"a", "application/json", "https://x", now, 200)
    r2 = RawResponse(b"b", "application/json", "https://x", now, 200)

    d1, _ = await store.save("statsbomb", "competitions", r1)
    d2, _ = await store.save("statsbomb", "competitions", r2)

    assert d1 != d2
