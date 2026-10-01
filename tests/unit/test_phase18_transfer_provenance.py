"""Phase 18 (R21): transfer provenance is classified from lineage, never upgraded."""
from __future__ import annotations

import uuid
from pathlib import Path

from app.normalization.service import transfer_provenance_status

ROOT = Path(__file__).resolve().parents[2]


def test_only_snapshotted_api_football_rows_are_verified():
    snap = uuid.uuid4()
    assert transfer_provenance_status("api-football", snap) == "VERIFIED_SOURCE"
    assert transfer_provenance_status("api-football", None) == "SOURCE_UNVERIFIED"
    # hand-curated lists stay unverified even if someone stores them as a "snapshot"
    assert transfer_provenance_status("open-transfer-archive", snap) == "SOURCE_UNVERIFIED"
    assert transfer_provenance_status("open-transfers", snap) == "SOURCE_UNVERIFIED"


def test_curation_tools_never_write_bronze_or_claim_verification():
    for name in ("curate_open_transfers.py", "curate_open_transfers_phase_4_1d.py"):
        src = (ROOT / "tools" / name).read_text()
        assert '"bronze"' not in src, name
        assert "zero_fabrication_audit" not in src and "PASSED" not in src, name
        assert '"provenance_status": "SOURCE_UNVERIFIED"' in src and '"license": "UNVERIFIED"' in src, name
