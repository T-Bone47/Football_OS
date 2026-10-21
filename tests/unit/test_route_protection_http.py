"""HTTP-level route protection. Needs the real web stack (starlette/FastAPI): NOT runnable in the audit sandbox, so it is
kept apart from the static checks in test_route_protection.py and recorded as not-run there; CI runs it."""
from __future__ import annotations

import re

import pytest

from test_route_protection import PUBLIC_PROBES  # noqa: E402  (shared allowlist)


@pytest.mark.real_auth
def test_every_non_public_route_rejects_unauthenticated_requests():
    from starlette.testclient import TestClient

    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    public = {("GET", p) for p in PUBLIC_PROBES} | {("GET", "/docs"), ("GET", "/redoc"), ("GET", "/openapi.json"), ("GET", "/docs/oauth2-redirect")}
    failures = []
    for route in app.routes:
        methods, path = getattr(route, "methods", None), getattr(route, "path", None)
        if not methods or not path:
            continue
        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            if (method, path) in public:
                continue
            status = client.request(method, re.sub(r"\{[^}]+\}", "x", path)).status_code
            if status != 401:
                failures.append((method, path, status))
    assert not failures, f"{len(failures)} routes did not answer 401 without a token: {failures[:10]}"


@pytest.mark.real_auth
def test_whoami_reports_only_the_verified_token():
    from auth_helpers import auth_headers
    from starlette.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    assert client.get("/api/v1/whoami").status_code == 401
    body = client.get("/api/v1/whoami", headers=auth_headers(user_id="u1", roles=("analyst",), org="org_x")).json()
    assert (body["user_id"], body["org_id"], body["roles"]) == ("u1", "org_x", ["analyst"])
    assert client.get("/api/v1/whoami", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
