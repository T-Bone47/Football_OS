"""Provider connectivity diagnostics (connectivity-forensics doc §15/§26).

Run as: python -m app.providers.diagnostics

Never prints a credential value — only SET/MISSING, and only the sanitized
parts of any error response. `run_diagnostics()` returns a plain dataclass
so the classification logic is unit-testable without a real network call
(tests/unit/test_diagnostics.py mocks the transport).
"""
from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass, field

import httpx

from app.config import Settings, get_settings


@dataclass
class ProviderDiagnostics:
    provider: str
    base_url: str
    dns: str = "NOT RUN"
    tls: str = "NOT RUN"
    http_reachable: str = "NOT RUN"
    credential_present: str = "MISSING"
    authentication: str = "UNKNOWN"
    authorization: str = "UNKNOWN"
    quota: str = "UNKNOWN"
    reason: str = ""
    http_status: int | None = None


def _check_dns(hostname: str) -> str:
    try:
        socket.getaddrinfo(hostname, 443)
        return "PASS"
    except socket.gaierror:
        return "FAIL"


async def _probe(base_url: str, path: str, headers: dict[str, str] | None) -> httpx.Response | Exception:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            return await client.get(path, headers=headers or {})
    except httpx.TransportError as exc:
        return exc


async def diagnose_api_football(settings: Settings) -> ProviderDiagnostics:
    diag = ProviderDiagnostics(provider="API-Football", base_url=settings.api_football_base_url)
    hostname = httpx.URL(settings.api_football_base_url).host
    diag.dns = _check_dns(hostname)
    if diag.dns == "FAIL":
        diag.reason = "DNS FAILURE"
        return diag

    diag.credential_present = "SET" if settings.api_football_key else "MISSING"

    unauth = await _probe(settings.api_football_base_url, "/status", None)
    if isinstance(unauth, Exception):
        diag.tls = "FAIL"
        diag.http_reachable = "FAIL"
        diag.reason = f"NETWORK/TLS FAILURE: {type(unauth).__name__}"
        return diag
    diag.tls = "PASS"
    diag.http_status = unauth.status_code

    if unauth.status_code == 403 and unauth.headers.get("x-deny-reason") == "host_not_allowed":
        diag.http_reachable = "FAIL"
        diag.reason = (
            "SANDBOX EGRESS POLICY BLOCK — this environment's own proxy rejected the "
            "host before the request reached API-Football. Not a DNS, TLS, auth, or "
            "rate-limit issue on API-Football's side."
        )
        return diag

    diag.http_reachable = "PASS"

    if diag.credential_present == "MISSING":
        diag.authentication = "UNKNOWN"
        diag.reason = "API HOST REACHABLE, AUTHENTICATION KEY MISSING"
        return diag

    authed = await _probe(
        settings.api_football_base_url, "/status", {"x-apisports-key": settings.api_football_key}
    )
    if isinstance(authed, Exception):
        diag.reason = f"NETWORK/TLS FAILURE on authenticated request: {type(authed).__name__}"
        return diag
    diag.http_status = authed.status_code

    if authed.status_code == 401:
        diag.authentication = "FAIL"
        diag.reason = "API HOST REACHABLE, KEY SUPPLIED, KEY REJECTED"
    elif authed.status_code == 403:
        diag.authentication = "PASS"
        diag.authorization = "FAIL"
        diag.reason = "AUTHENTICATION OK, AUTHORIZATION BLOCKED (IP/domain restriction or plan scope)"
    elif authed.status_code == 429:
        diag.reason = "RATE LIMITED"
        diag.quota = "EXHAUSTED"
    elif authed.status_code == 200:
        diag.authentication = "PASS"
        diag.authorization = "PASS"
        diag.quota = "AVAILABLE"
        diag.reason = "Authenticated API request succeeded."
    else:
        diag.reason = f"UNCLASSIFIED HTTP {authed.status_code}"

    return diag


async def diagnose_football_data_org(settings: Settings) -> ProviderDiagnostics:
    diag = ProviderDiagnostics(provider="football-data.org", base_url=settings.football_data_base_url)
    hostname = httpx.URL(settings.football_data_base_url).host
    diag.dns = _check_dns(hostname)
    if diag.dns == "FAIL":
        diag.reason = "DNS FAILURE"
        return diag

    diag.credential_present = "SET" if settings.football_data_token else "MISSING"

    unauth = await _probe(settings.football_data_base_url, "/areas", None)
    if isinstance(unauth, Exception):
        diag.tls = "FAIL"
        diag.http_reachable = "FAIL"
        diag.reason = f"NETWORK/TLS FAILURE: {type(unauth).__name__}"
        return diag
    diag.tls = "PASS"
    diag.http_status = unauth.status_code

    if unauth.status_code == 403 and unauth.headers.get("x-deny-reason") == "host_not_allowed":
        diag.http_reachable = "FAIL"
        diag.reason = (
            "SANDBOX EGRESS POLICY BLOCK — this environment's own proxy rejected the "
            "host before the request reached football-data.org."
        )
        return diag

    diag.http_reachable = "PASS"

    if diag.credential_present == "MISSING":
        diag.reason = "API HOST REACHABLE, TOKEN MISSING"
        return diag

    authed = await _probe(
        settings.football_data_base_url, "/areas", {"X-Auth-Token": settings.football_data_token}
    )
    if isinstance(authed, Exception):
        diag.reason = f"NETWORK/TLS FAILURE on authenticated request: {type(authed).__name__}"
        return diag
    diag.http_status = authed.status_code

    if authed.status_code == 400:
        diag.authentication = "FAIL"
        diag.reason = "API HOST REACHABLE, TOKEN SUPPLIED, TOKEN REJECTED"
    elif authed.status_code == 403:
        diag.authentication = "PASS"
        diag.authorization = "FAIL"
        diag.reason = "AUTHENTICATION OK, AUTHORIZATION BLOCKED"
    elif authed.status_code == 429:
        diag.reason = "RATE LIMITED"
        diag.quota = "EXHAUSTED"
    elif authed.status_code == 200:
        diag.authentication = "PASS"
        diag.authorization = "PASS"
        diag.quota = "AVAILABLE"
        diag.reason = "Authenticated API request succeeded."
    else:
        diag.reason = f"UNCLASSIFIED HTTP {authed.status_code}"

    return diag


def _format(diag: ProviderDiagnostics) -> str:
    lines = [
        diag.provider,
        "-" * len(diag.provider),
        f"Base URL: {diag.base_url}",
        "",
        f"DNS: {diag.dns}",
        f"TLS: {diag.tls}",
        f"HTTP Reachability: {diag.http_reachable}",
        f"Credential: {diag.credential_present}",
        f"Authentication: {diag.authentication}",
        f"Authorization: {diag.authorization}",
        f"Quota: {diag.quota}",
        "",
        "Reason:",
        diag.reason,
    ]
    return "\n".join(lines)


async def _main() -> None:
    settings = get_settings()
    api_football, football_data = await asyncio.gather(
        diagnose_api_football(settings), diagnose_football_data_org(settings)
    )
    print("FOOTBALL INTELLIGENCE OS")
    print("PROVIDER CONNECTIVITY DIAGNOSTICS")
    print("=" * 33)
    print()
    print(_format(api_football))
    print()
    print(_format(football_data))


if __name__ == "__main__":
    asyncio.run(_main())
