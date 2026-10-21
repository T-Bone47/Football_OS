"""HTTP-level demo gate test. Needs the real web stack (starlette/FastAPI): it is NOT runnable in the audit sandbox,
so it lives in its own file and is recorded as not-run there; CI runs it."""
from __future__ import annotations

import pytest


@pytest.mark.real_auth
def test_gated_routes_answer_409_demo_only_outside_demo_mode(monkeypatch):
    from auth_helpers import auth_headers
    from starlette.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    headers = auth_headers(user_id="u1", roles=("analyst",), org="org_a")
    monkeypatch.delenv("FOOTBALL_OS_DEMO_DATA", raising=False)
    for path in ("/api/v1/outcomes/ledger", "/api/v1/decision-lab/squad/arsenal_fc"):
        res = client.get(path, headers=headers)
        assert res.status_code == 409 and res.json()["detail"]["code"] == "DEMO_ONLY", path
    monkeypatch.setenv("FOOTBALL_OS_DEMO_DATA", "1")
    res = client.get("/api/v1/outcomes/ledger", headers=headers)
    assert res.status_code == 200 and res.headers["X-Data-Origin"] == "DEMO_FIXTURE"
