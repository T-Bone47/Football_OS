"""Authentication core (handoff §7.8): identity only from a verified signed token; fail closed."""
from __future__ import annotations

import time

import jwt
import pytest

from app.security.revocation import RevocationList
from app.security.tokens import AuthError, Principal, extract_bearer, require_permission, verify_token

SECRET = "s" * 40
ISS, AUD = "football-os-identity", "football-os-api"


def _token(secret: str = SECRET, **overrides) -> str:
    now = int(time.time())
    claims = {"sub": "user_42", "iss": ISS, "aud": AUD, "iat": now, "exp": now + 600, "jti": "jti-1",
              "roles": ["Scout"], "org": "org_a", "email": "a@b.co"}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, secret, algorithm="HS256")


def _verify(token: str, secret: str | None = SECRET, **kw) -> Principal:
    return verify_token(token, secret=secret, issuer=ISS, audience=AUD, **kw)


def test_valid_token_yields_principal_with_normalised_roles():
    p = _verify(_token())
    assert (p.user_id, p.org_id, p.email) == ("user_42", "org_a", "a@b.co")
    assert p.roles == frozenset({"scout"})
    assert "project:manage" in p.permissions and "model:promote" not in p.permissions


@pytest.mark.parametrize("secret", [None, "", "too-short"])
def test_unconfigured_or_weak_secret_fails_closed_503(secret):
    with pytest.raises(AuthError) as exc:
        _verify(_token(), secret=secret)
    assert exc.value.status_code == 503 and exc.value.code == "AUTH_NOT_CONFIGURED"


def test_wrong_signature_rejected():
    with pytest.raises(AuthError) as exc:
        _verify(_token(secret="x" * 40))
    assert exc.value.status_code == 401 and exc.value.code == "TOKEN_INVALID"


def test_expired_token_rejected():
    now = int(time.time())
    with pytest.raises(AuthError) as exc:
        _verify(_token(iat=now - 700, exp=now - 100))  # expired well beyond the 30 s skew allowance
    assert exc.value.code == "TOKEN_EXPIRED"


def test_expiry_has_exactly_the_documented_skew_allowance():
    now = int(time.time())
    assert _verify(_token(iat=now - 610, exp=now - 10)).user_id == "user_42"  # 10 s past exp: within the 30 s leeway
    with pytest.raises(AuthError):
        _verify(_token(iat=now - 610, exp=now - 60))


def test_alg_none_token_rejected():
    unsigned = jwt.encode({"sub": "u", "iss": ISS, "aud": AUD, "exp": int(time.time()) + 600}, key=None, algorithm="none")
    with pytest.raises(AuthError) as exc:
        _verify(unsigned)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("override", [{"iss": "evil"}, {"aud": "other-api"}, {"sub": None}, {"exp": None}, {"jti": None}, {"iat": None}])
def test_wrong_or_missing_required_claims_rejected(override):
    with pytest.raises(AuthError) as exc:
        _verify(_token(**override))
    assert exc.value.status_code == 401


@pytest.mark.parametrize("roles", ["admin", [1, 2], {"a": 1}])
def test_malformed_roles_claim_rejected(roles):
    with pytest.raises(AuthError):
        _verify(_token(roles=roles))


def test_unknown_role_grants_nothing():
    p = _verify(_token(roles=["superuser"]))
    assert p.permissions == frozenset()
    with pytest.raises(AuthError) as exc:
        require_permission(p, "data:read")
    assert exc.value.status_code == 403


def test_admin_can_promote_viewer_cannot():
    require_permission(_verify(_token(roles=["admin"])), "model:promote")
    with pytest.raises(AuthError) as exc:
        require_permission(_verify(_token(roles=["viewer"])), "model:promote")
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.parametrize(
    "header,expected",
    [("Bearer abc", "abc"), ("bearer  abc ", "abc"), ("Basic abc", None), ("Bearer", None), ("", None), (None, None)],
)
def test_extract_bearer(header, expected):
    assert extract_bearer(header) == expected


# ---------------------------------------------------------------- token lifecycle policy
def test_tokens_longer_lived_than_the_policy_maximum_are_rejected():
    now = int(time.time())
    with pytest.raises(AuthError) as exc:
        _verify(_token(iat=now, exp=now + 7 * 24 * 3600))
    assert exc.value.code == "TOKEN_TOO_LONG_LIVED"


def test_a_small_clock_skew_is_tolerated_but_not_a_large_one():
    now = int(time.time())
    assert _verify(_token(iat=now + 10, exp=now + 600)).user_id == "user_42"  # issued 10 s "in the future": skew
    with pytest.raises(AuthError):
        _verify(_token(iat=now + 3600, exp=now + 4200))


def test_the_previous_secret_is_accepted_during_rotation_and_only_then():
    old_secret = "o" * 40
    token = _token(secret=old_secret)
    with pytest.raises(AuthError):
        _verify(token)
    assert _verify(token, previous_secrets=(old_secret,)).user_id == "user_42"
    with pytest.raises(AuthError):
        _verify(_token(secret="z" * 40), previous_secrets=(old_secret,))


def test_a_revoked_token_id_is_rejected():
    revocations = RevocationList()
    token = _token(jti="stolen-1")
    assert _verify(token, revocations=revocations).user_id == "user_42"
    revocations.revoke_jti("stolen-1")
    with pytest.raises(AuthError) as exc:
        _verify(token, revocations=revocations)
    assert (exc.value.status_code, exc.value.code) == (401, "TOKEN_REVOKED")
    assert _verify(_token(jti="other"), revocations=revocations).user_id == "user_42"


def test_subject_wide_revocation_rejects_older_tokens_but_not_newer_ones():
    """Logout-everywhere / incident response: everything issued to a user before `not_before` stops working."""
    revocations = RevocationList()
    now = int(time.time())
    old = _token(iat=now - 120, exp=now + 480, jti="a")
    revocations.revoke_subject("user_42", not_before=now - 60)
    with pytest.raises(AuthError) as exc:
        _verify(old, revocations=revocations)
    assert exc.value.code == "TOKEN_REVOKED"
    assert _verify(_token(iat=now, exp=now + 600, jti="b"), revocations=revocations).user_id == "user_42"
    other_user = _token(sub="user_99", iat=now - 120, exp=now + 480, jti="c")
    assert _verify(other_user, revocations=revocations).user_id == "user_99"


def test_revocation_list_is_bounded_in_time_by_token_lifetime():
    """Entries only need to outlive the longest token, so expired ones are pruned (the list cannot grow forever)."""
    revocations = RevocationList()
    revocations.revoke_jti("old", expires_at=int(time.time()) - 10)
    revocations.revoke_jti("live", expires_at=int(time.time()) + 600)
    assert revocations.prune() == 1
    assert revocations.is_revoked("live", "u", 0) and not revocations.is_revoked("old", "u", 0)
