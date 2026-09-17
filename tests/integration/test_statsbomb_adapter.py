"""Real network test — hits raw.githubusercontent.com. This is the one
provider this sandbox can actually reach, so it's the one we can honestly
call live-verified rather than mock-verified.
"""
from pathlib import Path

from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.providers.statsbomb import StatsBombProvider


async def test_fetch_real_statsbomb_competitions(tmp_path: Path):
    provider = StatsBombProvider()
    response = await provider.fetch("competitions")

    assert response.status_code == 200
    assert response.content.strip().startswith(b"[")

    store = LocalFilesystemSnapshotStore(tmp_path)
    digest, path = await store.save("statsbomb", "competitions", response)

    assert len(digest) == 64
    assert Path(path).exists()
    await provider.close()
