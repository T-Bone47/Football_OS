"""Mint real HS256 tokens for tests that exercise authentication (marked @pytest.mark.real_auth)."""
from __future__ import annotations

import os
import time
import uuid

import jwt


def make_token(user_id: str = "user_1", roles: tuple[str, ...] = ("scout",), org: str | None = "org_a", ttl: int = 600, **extra) -> str:
    now = int(time.time())
    claims = {
        "sub": user_id,
        "iss": os.environ.get("AUTH_JWT_ISSUER", "football-os-identity"),
        "aud": os.environ.get("AUTH_JWT_AUDIENCE", "football-os-api"),
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
        "roles": list(roles),
    }
    if org is not None:
        claims["org"] = org
    claims.update(extra)
    return jwt.encode(claims, os.environ["AUTH_JWT_SECRET"], algorithm="HS256")


def auth_headers(**kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(**kwargs)}"}
