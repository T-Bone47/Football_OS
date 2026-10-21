"""Pure helpers for the identity service: sign-in allowlist and the short-lived API access token.

The access token is what apps/api verifies (app.security.tokens): HS256, claims
sub / iss / aud / exp / roles / org / email, signed with the shared AUTH_JWT_SECRET (>= 32 bytes).
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Iterable

import jwt

MIN_SECRET_BYTES = 32
VALID_ROLES = ("admin", "analyst", "scout", "researcher", "viewer")


def parse_csv(raw: str | None) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def email_allowed(email: str, allowed_emails: Iterable[str], allowed_domains: Iterable[str]) -> bool:
    """Fail closed: with neither list configured nobody may sign in (Google accounts are open to the world)."""
    emails = {e.strip().lower() for e in allowed_emails if e.strip()}
    domains = {d.strip().lower().lstrip("@") for d in allowed_domains if d.strip()}
    if not emails and not domains:
        return False
    address = email.strip().lower()
    return address in emails or address.rpartition("@")[2] in domains  # exact domain match, no suffix tricks


def mint_access_token(
    *,
    user: dict,
    secret: str | None,
    issuer: str,
    audience: str,
    default_role: str = "viewer",
    ttl_seconds: int = 900,
    now: int | None = None,
) -> str:
    if not secret or len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
        raise RuntimeError("AUTH_JWT_SECRET must be set and at least 32 bytes")
    if default_role not in VALID_ROLES:
        raise ValueError(f"unknown default role {default_role!r}")
    issued = int(time.time()) if now is None else now
    roles = [r for r in (user.get("roles") or [default_role]) if r in VALID_ROLES] or [default_role]
    claims = {
        "sub": user["user_id"],
        "iss": issuer,
        "aud": audience,
        "iat": issued,
        "exp": issued + ttl_seconds,
        "jti": uuid.uuid4().hex,
        "roles": roles,
    }
    if user.get("email"):
        claims["email"] = user["email"]
    if user.get("org_id"):
        claims["org"] = user["org_id"]
    return jwt.encode(claims, secret, algorithm="HS256")
