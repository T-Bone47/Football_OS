"""Contract between the identity service (mints access tokens) and apps/api (verifies them), plus the sign-in allowlist."""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import jwt
import pytest

from app.security.tokens import AuthError, verify_token

_PATH = Path(__file__).resolve().parents[2] / "Football_OS-frontend" / "backend" / "auth_tokens.py"
_spec = importlib.util.spec_from_file_location("identity_auth_tokens", _PATH)
identity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(identity)

SECRET = "i" * 40
ISS, AUD = "football-os-identity", "football-os-api"
USER = {"user_id": "user_abc", "email": "scout@club.example", "org_id": "org_a", "roles": ["scout"]}


def _mint(**overrides):
    args = dict(user=USER, secret=SECRET, issuer=ISS, audience=AUD)
    args.update(overrides)
    return identity.mint_access_token(**args)


def test_a_minted_token_is_accepted_by_the_api_with_the_same_identity():
    principal = verify_token(_mint(), secret=SECRET, issuer=ISS, audience=AUD)
    assert (principal.user_id, principal.org_id, principal.email) == ("user_abc", "org_a", "scout@club.example")
    assert principal.roles == frozenset({"scout"})


def test_unknown_roles_in_the_user_record_are_dropped_and_default_is_least_privilege():
    token = _mint(user={**USER, "roles": ["superuser"]})
    assert verify_token(token, secret=SECRET, issuer=ISS, audience=AUD).roles == frozenset({"viewer"})
    assert verify_token(_mint(user={"user_id": "u"}), secret=SECRET, issuer=ISS, audience=AUD).roles == frozenset({"viewer"})


def test_tokens_are_short_lived():
    now = int(time.time())
    claims = jwt.decode(_mint(now=now), SECRET, algorithms=["HS256"], audience=AUD)
    assert claims["exp"] - claims["iat"] == 900


def test_a_token_signed_with_a_different_secret_is_rejected_by_the_api():
    with pytest.raises(AuthError):
        verify_token(_mint(secret="j" * 40), secret=SECRET, issuer=ISS, audience=AUD)


@pytest.mark.parametrize("secret", [None, "", "short"])
def test_minting_refuses_without_a_strong_secret(secret):
    with pytest.raises(RuntimeError):
        _mint(secret=secret)


def test_minting_rejects_an_unknown_default_role():
    with pytest.raises(ValueError):
        _mint(default_role="root")


@pytest.mark.parametrize(
    "email,emails,domains,expected",
    [
        ("a@club.example", [], [], False),  # nothing configured => nobody (fail closed)
        ("a@club.example", ["a@club.example"], [], True),
        ("A@Club.Example", ["a@club.example"], [], True),
        ("b@club.example", ["a@club.example"], [], False),
        ("b@club.example", [], ["club.example"], True),
        ("b@club.example", [], ["@club.example"], True),
        ("b@evilclub.example", [], ["club.example"], False),  # no suffix matching
        ("b@club.example.evil.com", [], ["club.example"], False),
    ],
)
def test_signin_allowlist_is_exact_and_fails_closed(email, emails, domains, expected):
    assert identity.email_allowed(email, emails, domains) is expected


def test_every_minted_token_has_a_unique_id_for_revocation():
    ids = {jwt.decode(_mint(), SECRET, algorithms=["HS256"], audience=AUD)["jti"] for _ in range(5)}
    assert len(ids) == 5
