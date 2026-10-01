"""Phase 18 — deny by default (R9): every operation refuses an anonymous caller.

Sweeps the live OpenAPI schema, so a new route is covered the moment it is
added. Only the liveness/readiness probes and the API schema are public.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.auth_gate import PUBLIC_PATHS, demo_only_match
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def _operations():
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            yield method.upper(), path


OPERATIONS = sorted(_operations())


def test_sweep_is_not_empty():
    assert len(OPERATIONS) > 250


@pytest.mark.parametrize("method,path", OPERATIONS, ids=[f"{m} {p}" for m, p in OPERATIONS])
def test_anonymous_is_refused(method, path):
    if path in PUBLIC_PATHS:
        pytest.skip("public probe")
    concrete = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", path)
    resp = client.request(method, concrete, json={} if method in ("POST", "PUT", "PATCH") else None)
    # 401: authentication required. 410: an in-memory route retired outside
    # demo mode (nothing is served either way).
    assert resp.status_code in (401, 410), (method, path, resp.status_code, resp.text[:200])
    if resp.status_code == 410:
        assert demo_only_match(method, concrete) is not None


def test_body_user_id_cannot_authenticate():
    resp = client.post("/api/v1/projects", json={"user_id": "admin_01", "name": "x"})
    assert resp.status_code in (401, 410)
    resp = client.get("/api/auth/me", headers={"X-User-Id": "admin_01"})
    assert resp.status_code == 401


def test_forged_tokens_are_refused():
    # JWT-shaped tokens are refused before any lookup (no OIDC issuer is
    # configured here, and alg=none is never accepted).
    for token in ("a.b.c", "eyJhbGciOiJub25lIn0.eyJzdWIiOiJ4In0."):
        resp = client.get("/api/v1/players", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401, token
    # An opaque token needs the database. Without one the API fails closed
    # with 503, never 200 and never an unhandled 500 (integration tests
    # check the 401 with a database).
    resp = client.get("/api/v1/players", headers={"Authorization": "Bearer forged"})
    assert resp.status_code in (401, 503)
