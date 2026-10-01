"""API contract gate (§47): the /api/v1/ops surface must match the reviewed
contract in tests/contracts/ops_api_contract.json, and every operation must
refuse an anonymous caller (401, or 422 when the request is malformed
before authentication is reached; neither returns data)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "phase17"))

from export_api_contract import contract  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_ops_api_matches_reviewed_contract():
    reviewed = json.loads((ROOT / "tests" / "contracts" / "ops_api_contract.json").read_text())
    current = contract()
    assert sorted(current) == sorted(reviewed), "operations added or removed without updating the contract"
    assert current == reviewed, "parameters or request bodies changed without updating the contract"


def test_every_ops_operation_rejects_anonymous_callers():
    client = TestClient(app)
    for op in contract():
        method, path = op.split(" ", 1)
        concrete = path.replace("{match_id}", "00000000-0000-0000-0000-000000000000") \
            .replace("{inference_id}", "00000000-0000-0000-0000-000000000000") \
            .replace("{project_id}", "00000000-0000-0000-0000-000000000000") \
            .replace("{watchlist_id}", "00000000-0000-0000-0000-000000000000") \
            .replace("{decision_id}", "00000000-0000-0000-0000-000000000000") \
            .replace("{alert_id}", "00000000-0000-0000-0000-000000000000") \
            .replace("{competition_season_id}", "00000000-0000-0000-0000-000000000000") \
            .replace("{model_id}", "m").replace("{action}", "acknowledge")
        r = client.request(method, concrete, json={})
        assert r.status_code in (401, 422), f"{op} answered {r.status_code} without a token"
