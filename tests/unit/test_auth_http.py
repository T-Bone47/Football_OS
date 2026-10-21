"""End-to-end authentication over HTTP with REAL tokens (stage 2, item 5). Needs the web stack: NOT runnable in the
audit sandbox; CI runs it. Unit-level coverage of the same rules (no web stack) is in test_security_tokens.py and
test_identity_token_contract.py."""
from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from auth_helpers import auth_headers, make_token
from starlette.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.real_auth
client = TestClient(app)
PROJECT = {"name": "p", "club": "c", "season": "2026/27", "position": "CB", "target_role": "r"}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_missing_malformed_and_garbage_credentials_are_401():
    assert client.get("/api/v1/whoami").status_code == 401
    assert client.get("/api/v1/whoami", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/api/v1/whoami", headers=_bearer("not.a.jwt")).status_code == 401


def test_expired_wrong_audience_wrong_issuer_and_unsigned_tokens_are_401():
    now = int(time.time())
    assert client.get("/api/v1/whoami", headers=_bearer(make_token(iat=now - 900, exp=now - 300))).status_code == 401
    assert client.get("/api/v1/whoami", headers=_bearer(make_token(aud="someone-else"))).status_code == 401
    assert client.get("/api/v1/whoami", headers=_bearer(make_token(iss="evil"))).status_code == 401
    unsigned = jwt.encode({"sub": "u", "iss": "football-os-identity", "aud": "football-os-api", "iat": now, "exp": now + 60, "jti": "x"}, key=None, algorithm="none")
    assert client.get("/api/v1/whoami", headers=_bearer(unsigned)).status_code == 401


def test_a_server_without_a_configured_secret_fails_closed(monkeypatch):
    monkeypatch.setattr("app.security.deps.get_settings", lambda: SimpleNamespace(
        auth_jwt_secret=None, auth_jwt_secret_previous=None, auth_jwt_issuer="football-os-identity", auth_jwt_audience="football-os-api"))
    assert client.get("/api/v1/whoami", headers=auth_headers()).status_code == 503


def test_roles_are_enforced_by_the_server_not_the_ui():
    viewer = auth_headers(user_id="v", roles=("viewer",), org="org_a")
    analyst = auth_headers(user_id="a", roles=("analyst",), org="org_a")
    scout = auth_headers(user_id="s", roles=("scout",), org="org_a")
    admin = auth_headers(user_id="adm", roles=("admin",), org="org_a")
    assert client.post("/api/phase10/recruitment/projects", json=PROJECT, headers=viewer).status_code == 403
    assert client.post("/api/phase10/recruitment/projects", json=PROJECT, headers=analyst).status_code == 200
    assert client.get("/api/v1/audit", headers=scout).status_code == 403
    assert client.get("/api/v1/audit", headers=admin).status_code == 200
    assert client.post("/api/v1/admin/revocations", json={"jti": "x"}, headers=scout).status_code == 403


def test_revoking_a_token_id_blocks_that_token_immediately_and_only_that_token():
    victim = make_token(user_id="victim", jti="leaked-token-1")
    other = make_token(user_id="victim", jti="still-fine")
    assert client.get("/api/v1/whoami", headers=_bearer(victim)).status_code == 200
    res = client.post("/api/v1/admin/revocations", json={"jti": "leaked-token-1"}, headers=auth_headers(user_id="adm", roles=("admin",)))
    assert res.status_code == 200
    blocked = client.get("/api/v1/whoami", headers=_bearer(victim))
    assert blocked.status_code == 401
    assert client.get("/api/v1/whoami", headers=_bearer(other)).status_code == 200


def test_subject_revocation_blocks_older_tokens_but_not_newer_ones():
    now = int(time.time())
    old = make_token(user_id="carol", iat=now - 300, exp=now + 300)
    new = make_token(user_id="carol")
    admin = auth_headers(user_id="adm", roles=("admin",))
    assert client.post("/api/v1/admin/revocations", json={"user_id": "carol", "not_before": now - 60}, headers=admin).status_code == 200
    assert client.get("/api/v1/whoami", headers=_bearer(old)).status_code == 401
    assert client.get("/api/v1/whoami", headers=_bearer(new)).status_code == 200


def test_revocation_requests_must_name_exactly_one_target():
    admin = auth_headers(user_id="adm", roles=("admin",))
    assert client.post("/api/v1/admin/revocations", json={}, headers=admin).status_code == 422
    assert client.post("/api/v1/admin/revocations", json={"jti": "a", "user_id": "b"}, headers=admin).status_code == 422


def test_a_token_minted_by_the_identity_service_is_accepted_by_the_api():
    path = Path(__file__).resolve().parents[2] / "Football_OS-frontend" / "backend" / "auth_tokens.py"
    spec = importlib.util.spec_from_file_location("identity_auth_tokens_http", path)
    identity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(identity)
    token = identity.mint_access_token(
        user={"user_id": "u_identity", "email": "u@club.example", "org_id": "org_x", "roles": ["analyst"]},
        secret=os.environ["AUTH_JWT_SECRET"], issuer="football-os-identity", audience="football-os-api",
    )
    body = client.get("/api/v1/whoami", headers=_bearer(token)).json()
    assert (body["user_id"], body["org_id"], body["roles"]) == ("u_identity", "org_x", ["analyst"])
