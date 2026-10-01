"""Phase 18 — authentication and RBAC against a real database (R9).

Real bearer tokens and real OIDC verification. The OIDC issuer here is a test
RSA key pair whose public half is served as the JWKS; signature, issuer,
audience and expiry are checked by the same code production uses.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import app.phase17.auth as auth
from app.config import Settings
from app.db.session import get_session
from app.main import app
from app.phase17 import OpsRole
from app.phase17.auth import issue_user

ISSUER, AUDIENCE = "https://idp.test.invalid/", "football-os"


@pytest.fixture
async def api(p17_session):
    async def override():
        async with p17_session.test_sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        yield client
    app.dependency_overrides.clear()


async def _user(session, role=OpsRole.ANALYST, org="Org A"):
    user, token = await issue_user(session, org, f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@example.test", "U", role)
    await session.commit()
    return user, {"Authorization": f"Bearer {token}"}


async def test_me_is_the_authenticated_principal(api, p17_session):
    user, h = await _user(p17_session)
    body = (await api.get("/api/auth/me", headers=h)).json()
    assert body["user_id"] == str(user.id) and body["auth_method"] == "BEARER_TOKEN"
    assert body["token_expires_at"] is not None
    assert (await api.get("/api/auth/me")).status_code == 401


async def test_forged_token_is_refused_with_a_database(api):
    assert (await api.get("/api/v1/players", headers={"Authorization": "Bearer forged"})).status_code == 401


async def test_expired_token_is_refused(api, p17_session):
    user, h = await _user(p17_session)
    user.token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await p17_session.commit()
    r = await api.get("/api/auth/me", headers=h)
    assert r.status_code == 401 and "expired" in r.json()["detail"]


async def test_logout_revokes_the_token(api, p17_session):
    _, h = await _user(p17_session)
    assert (await api.post("/api/auth/logout", headers=h)).status_code == 200
    r = await api.get("/api/auth/me", headers=h)
    assert r.status_code == 401 and "revoked" in r.json()["detail"]


async def test_rotation_invalidates_the_previous_token(api, p17_session):
    _, h = await _user(p17_session)
    new = (await api.post("/api/v1/ops/me/rotate-token", headers=h)).json()["token"]
    assert (await api.get("/api/auth/me", headers=h)).status_code == 401
    assert (await api.get("/api/auth/me", headers={"Authorization": f"Bearer {new}"})).status_code == 200


async def test_admin_revocation_is_scoped_to_the_organization(api, p17_session):
    target, th = await _user(p17_session, OpsRole.SCOUT, "Org A")
    _, other_admin = await _user(p17_session, OpsRole.ADMIN, "Org B")
    assert (await api.post(f"/api/v1/ops/users/{target.id}/revoke", headers=other_admin)).status_code == 404
    _, admin = await _user(p17_session, OpsRole.ADMIN, "Org A")
    assert (await api.post(f"/api/v1/ops/users/{target.id}/revoke", headers=admin)).status_code == 200
    assert (await api.get("/api/auth/me", headers=th)).status_code == 401


async def test_role_limits(api, p17_session):
    _, viewer = await _user(p17_session, OpsRole.VIEWER)
    _, analyst = await _user(p17_session, OpsRole.ANALYST)
    # reads are allowed, compute and ingestion are not
    assert (await api.get("/api/v1/players", headers=viewer)).status_code == 200
    assert (await api.post("/api/v1/tactical-fit/compare", headers=viewer, json={})).status_code == 403
    assert (await api.post("/api/v1/normalization/snapshots/" + str(uuid.uuid4()), headers=analyst)).status_code == 403
    # escalation: an analyst cannot mint users or promote models
    assert (await api.post("/api/v1/ops/users", headers=analyst,
                           json={"email": "x@example.test", "name": "x", "role": "ADMIN"})).status_code == 403
    assert (await api.post(f"/api/v1/ops/models/{uuid.uuid4()}/promote", headers=analyst,
                           json={"target_state": "ACTIVE", "reason": "x"})).status_code == 403


async def test_in_memory_routes_are_retired_outside_demo_mode(api, p17_session, monkeypatch):
    import app.dev_fixtures as fx

    monkeypatch.setattr(fx, "get_settings", lambda: Settings(_env_file=None, dev_seed=False))
    _, h = await _user(p17_session, OpsRole.ADMIN)
    r = await api.post("/api/v1/projects", headers=h, json={"user_id": "admin_01", "name": "x"})
    assert r.status_code == 410 and r.json()["detail"]["status"] == "RETIRED_IN_MEMORY_STATE"
    assert (await api.get("/api/phase10/watchlists", headers=h)).status_code == 410


# ----------------------------------------------------------------------- OIDC
@pytest.fixture
def idp(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="k1", use="sig", alg="RS256")
    settings = Settings(_env_file=None, oidc_issuer=ISSUER, oidc_audience=AUDIENCE,
                        oidc_jwks_url="https://idp.test.invalid/jwks")
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    async def _jwks(url):
        assert url == "https://idp.test.invalid/jwks"
        return [jwk]

    monkeypatch.setattr(auth, "_jwks", _jwks)

    def sign(sub="user-123", aud=AUDIENCE, iss=ISSUER, exp_in=300, signer=key, kid="k1"):
        now = int(time.time())
        return jwt.encode({"sub": sub, "aud": aud, "iss": iss, "iat": now, "exp": now + exp_in},
                          signer, algorithm="RS256", headers={"kid": kid})
    return sign


async def test_oidc_token_maps_to_a_provisioned_user(api, p17_session, idp):
    user, _ = await _user(p17_session, OpsRole.SCOUT)
    user.oidc_issuer, user.oidc_subject = ISSUER, "user-123"
    await p17_session.commit()
    r = await api.get("/api/auth/me", headers={"Authorization": f"Bearer {idp()}"})
    assert r.status_code == 200 and r.json()["user_id"] == str(user.id) and r.json()["auth_method"] == "OIDC"


async def test_oidc_rejections(api, p17_session, idp):
    user, _ = await _user(p17_session, OpsRole.SCOUT)
    user.oidc_issuer, user.oidc_subject = ISSUER, "user-123"
    await p17_session.commit()
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cases = {
        "wrong audience": idp(aud="another-app"),
        "wrong issuer": idp(iss="https://evil.invalid/"),
        "expired": idp(exp_in=-10),
        "bad signature": idp(signer=other_key),
        "unknown key id": idp(kid="nope"),
    }
    for name, token in cases.items():
        r = await api.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, name
    r = await api.get("/api/auth/me", headers={"Authorization": f"Bearer {idp(sub='never-provisioned')}"})
    assert r.status_code == 403
