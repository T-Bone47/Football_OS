"""Diagnostics classification logic, tested against a MOCKED transport —
covers the cases a live network can't safely reproduce on demand (401, 403
IP-restriction, 429) alongside the one this sandbox reproduces for real."""
import httpx
import pytest

from app.config import Settings
from app.providers.diagnostics import diagnose_api_football


def _settings(**overrides) -> Settings:
    return Settings(
        api_football_key=overrides.get("api_football_key", "test-key"),
        api_football_base_url=overrides.get("api_football_base_url", "https://v3.football.api-sports.io"),
        football_data_token=None,
        _env_file=None,
    )


async def _diagnose_with_responses(monkeypatch, responses: list[httpx.Response]):
    calls = iter(responses)

    async def fake_probe(base_url, path, headers):
        return next(calls)

    monkeypatch.setattr("app.providers.diagnostics._probe", fake_probe)
    return await diagnose_api_football(_settings())


def _ok_dns(monkeypatch):
    monkeypatch.setattr("app.providers.diagnostics._check_dns", lambda host: "PASS")


async def test_sandbox_deny_reason_is_classified_precisely(monkeypatch):
    _ok_dns(monkeypatch)
    req = httpx.Request("GET", "https://x")
    deny = httpx.Response(403, request=req, headers={"x-deny-reason": "host_not_allowed"})
    diag = await _diagnose_with_responses(monkeypatch, [deny])
    assert diag.http_reachable == "FAIL"
    assert "SANDBOX EGRESS POLICY BLOCK" in diag.reason


async def test_missing_key_reachable_host_is_distinct_from_blocked(monkeypatch):
    _ok_dns(monkeypatch)
    req = httpx.Request("GET", "https://x")
    missing_key_403 = httpx.Response(403, request=req, headers={}, json={"message": "Missing application key"})

    calls = iter([missing_key_403])

    async def fake_probe(base_url, path, headers):
        return next(calls)

    monkeypatch.setattr("app.providers.diagnostics._probe", fake_probe)
    diag = await diagnose_api_football(_settings(api_football_key=None))

    assert diag.http_reachable == "PASS"
    assert "SANDBOX EGRESS" not in diag.reason


async def test_valid_key_authenticated_success(monkeypatch):
    _ok_dns(monkeypatch)
    req = httpx.Request("GET", "https://x")
    unauth_403 = httpx.Response(403, request=req, json={"message": "Missing application key"})
    authed_200 = httpx.Response(200, request=req, json={"response": "ok"})
    diag = await _diagnose_with_responses(monkeypatch, [unauth_403, authed_200])
    assert diag.authentication == "PASS"
    assert diag.authorization == "PASS"
    assert diag.quota == "AVAILABLE"


async def test_key_present_but_rejected(monkeypatch):
    _ok_dns(monkeypatch)
    req = httpx.Request("GET", "https://x")
    unauth_403 = httpx.Response(403, request=req, json={"message": "Missing application key"})
    authed_401 = httpx.Response(401, request=req)
    diag = await _diagnose_with_responses(monkeypatch, [unauth_403, authed_401])
    assert diag.authentication == "FAIL"
    assert "REJECTED" in diag.reason
