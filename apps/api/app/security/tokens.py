"""Bearer-token authentication (handoff §7.8 / §10.1).

Identity is derived ONLY from a signed token verified here. No function in this module (or
its callers) may take a user id from a request body/query. Auth that is not configured fails
closed (503); there is no development bypass and no default user.

Token contract (HS256, shared secret AUTH_JWT_SECRET, >= 32 bytes):
  required claims: sub (user id), exp, iat, jti (unique token id), iss, aud
  optional claims: roles (list[str]), org (str), email (str)

Lifecycle policy: a token may live at most MAX_TOKEN_TTL_SECONDS (exp - iat); 30 s of clock skew is tolerated; the
previous secret is accepted during key rotation (AUTH_JWT_SECRET_PREVIOUS); revoked ids/subjects are rejected
(app.security.revocation).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import jwt  # PyJWT

from app.security.permissions import permissions_for
from app.security.revocation import LEEWAY_SECONDS, MAX_TOKEN_TTL_SECONDS, RevocationList

MIN_SECRET_BYTES = 32
_ALGORITHMS = ["HS256"]  # pinned: never accept "none" or an attacker-chosen alg


class AuthError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Principal:
    user_id: str
    roles: frozenset[str]
    org_id: str | None = None
    email: str | None = None
    token_id: str | None = None
    issued_at: int | None = None

    @property
    def permissions(self) -> frozenset[str]:
        return permissions_for(self.roles)


def extract_bearer(authorization: str | None) -> str | None:
    """Return the token from an 'Authorization: Bearer <token>' header, else None."""
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    value = value.strip()
    if scheme.lower() != "bearer" or not value:
        return None
    return value


def verify_token(
    token: str,
    *,
    secret: str | None,
    issuer: str,
    audience: str,
    previous_secrets: Sequence[str] = (),
    revocations: RevocationList | None = None,
) -> Principal:
    if not secret or len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
        raise AuthError(503, "AUTH_NOT_CONFIGURED", "authentication is not configured on this server")
    claims = None
    for key in (secret, *previous_secrets):
        if not key or len(key.encode("utf-8")) < MIN_SECRET_BYTES:
            continue
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=_ALGORITHMS,
                issuer=issuer,
                audience=audience,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "sub", "iss", "aud", "jti"]},
            )
            break
        except jwt.ExpiredSignatureError as exc:
            raise AuthError(401, "TOKEN_EXPIRED", "token expired") from exc
        except jwt.InvalidSignatureError:
            continue  # maybe signed with the previous secret (rotation)
        except jwt.PyJWTError as exc:
            raise AuthError(401, "TOKEN_INVALID", "invalid token") from exc
    if claims is None:
        raise AuthError(401, "TOKEN_INVALID", "invalid token")

    sub, jti, iat, exp = claims.get("sub"), claims.get("jti"), claims.get("iat"), claims.get("exp")
    roles = claims.get("roles", [])
    if not isinstance(sub, str) or not sub.strip() or not isinstance(jti, str) or not jti:
        raise AuthError(401, "TOKEN_INVALID", "invalid token")
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise AuthError(401, "TOKEN_INVALID", "invalid token")
    if not isinstance(iat, (int, float)) or not isinstance(exp, (int, float)):
        raise AuthError(401, "TOKEN_INVALID", "invalid token")
    if exp - iat > MAX_TOKEN_TTL_SECONDS:
        raise AuthError(401, "TOKEN_TOO_LONG_LIVED", "token lifetime exceeds the policy maximum")
    if revocations is not None and revocations.is_revoked(jti, sub, int(iat)):
        raise AuthError(401, "TOKEN_REVOKED", "token revoked")
    org = claims.get("org")
    email = claims.get("email")
    return Principal(
        user_id=sub,
        roles=frozenset(r.strip().lower() for r in roles),
        org_id=org if isinstance(org, str) and org else None,
        email=email if isinstance(email, str) and email else None,
        token_id=jti,
        issued_at=int(iat),
    )


def require_permission(principal: Principal, permission: str) -> None:
    if permission not in principal.permissions:
        raise AuthError(403, "FORBIDDEN", f"missing permission '{permission}'")
