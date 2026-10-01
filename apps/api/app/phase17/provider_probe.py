"""Real provider connectivity probes (§3).

A probe sends one real HTTP request and records exactly what came back.
Nothing here assumes availability: a provider with no probe row is UNKNOWN.

Classification:
- egress proxy refuses CONNECT (httpx.ProxyError)       -> BLOCKED
- DNS / TCP / TLS / timeout                              -> UNAVAILABLE
- 401/403 from the provider, or an auth error envelope   -> AUTH_FAILED
- 429                                                    -> RATE_LIMITED
- 404 for the probed resource                            -> CAPABILITY_UNAVAILABLE
- 5xx                                                    -> UNAVAILABLE
- 2xx with a usable body                                 -> AVAILABLE
- anything else                                          -> UNKNOWN
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.operations import ProviderProbe
from app.phase17 import ProviderConnectivityState as S

STATSBOMB_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


@dataclass(frozen=True)
class ProbeTarget:
    provider: str
    resource: str
    url: str
    auth_header: str | None = None
    credential_setting: str | None = None
    # Resources the probe's success demonstrates are reachable.
    capability: str | None = None


def default_targets(settings: Settings) -> list[ProbeTarget]:
    """One cheap request per provider/resource family. StatsBomb event files
    run to several MB per match, so events are evidenced by real ingestion
    runs rather than by a probe."""
    return [
        ProbeTarget("statsbomb", "competitions", f"{STATSBOMB_BASE}/competitions.json", capability="competitions"),
        # FIFA World Cup 2022 (competition 43, season 106): 64 matches, 119 KB.
        ProbeTarget("statsbomb", "matches", f"{STATSBOMB_BASE}/matches/43/106.json", capability="matches"),
        ProbeTarget("statsbomb", "lineups", f"{STATSBOMB_BASE}/lineups/3869685.json", capability="lineups"),
        ProbeTarget(
            "api-football", "status", f"{settings.api_football_base_url}/status",
            auth_header="x-apisports-key", credential_setting="api_football_key", capability="account_status",
        ),
        ProbeTarget(
            "football-data-org", "competitions", f"{settings.football_data_base_url}/competitions",
            auth_header="X-Auth-Token", credential_setting="football_data_token", capability="competitions",
        ),
    ]


@dataclass
class ProbeResult:
    provider: str
    resource: str
    endpoint: str
    state: str
    authentication_state: str
    http_status: int | None
    latency_ms: float | None
    quota: dict[str, Any] = field(default_factory=dict)
    capability: str | None = None
    detail: str | None = None
    probed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    response_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_QUOTA_HEADER_HINTS = ("ratelimit", "rate-limit", "requests", "quota", "retry-after")


def _quota_from_headers(headers: httpx.Headers) -> dict[str, Any]:
    return {k.lower(): v for k, v in headers.items() if any(h in k.lower() for h in _QUOTA_HEADER_HINTS)}


def _api_football_body_quota(body: Any) -> dict[str, Any]:
    if isinstance(body, dict):
        resp = body.get("response")
        if isinstance(resp, dict) and isinstance(resp.get("requests"), dict):
            return {"requests": resp["requests"]}
    return {}


def _envelope_errors(body: Any) -> Any:
    if isinstance(body, dict):
        errs = body.get("errors")
        if errs:
            return errs
    return None


def classify_response(target: ProbeTarget, response: httpx.Response, credential_present: bool) -> tuple[str, str, str | None]:
    """Returns (state, authentication_state, detail)."""
    status = response.status_code
    auth = "NOT_REQUIRED" if target.auth_header is None else ("PRESENTED" if credential_present else "MISSING_CREDENTIALS")
    if status in (401, 403):
        return S.AUTH_FAILED.value, ("REJECTED" if credential_present else auth), f"HTTP {status}"
    if status == 429:
        return S.RATE_LIMITED.value, auth, "HTTP 429"
    if status == 404:
        return S.CAPABILITY_UNAVAILABLE.value, auth, "HTTP 404 for probed resource"
    if status >= 500:
        return S.UNAVAILABLE.value, auth, f"HTTP {status}"
    if 200 <= status < 300:
        try:
            body = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return S.UNKNOWN.value, auth, "2xx with non-JSON body"
        errors = _envelope_errors(body)
        if errors:
            text = json.dumps(errors).lower()
            if "token" in text or "key" in text or "auth" in text:
                return S.AUTH_FAILED.value, ("REJECTED" if credential_present else auth), f"error envelope: {errors}"
            return S.CAPABILITY_UNAVAILABLE.value, auth, f"error envelope: {errors}"
        if target.auth_header is not None:
            auth = "ACCEPTED"
        return S.AVAILABLE.value, auth, None
    return S.UNKNOWN.value, auth, f"HTTP {status}"


async def probe_target(
    target: ProbeTarget,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> ProbeResult:
    credential = getattr(settings, target.credential_setting) if target.credential_setting else None
    headers = {target.auth_header: credential} if (target.auth_header and credential) else {}
    # When the request never reaches the provider, record whether a credential
    # was configured (never its value) so BLOCKED is not mistaken for "no key".
    not_attempted = "NOT_ATTEMPTED" if target.auth_header is None else (
        "NOT_ATTEMPTED_KEY_PRESENT" if credential else "NOT_ATTEMPTED_NO_KEY")
    owns = client is None
    client = client or httpx.AsyncClient(timeout=settings.provider_probe_timeout_s)
    started = time.perf_counter()
    try:
        response = await client.get(target.url, headers=headers)
    except httpx.ProxyError as exc:
        return ProbeResult(
            target.provider, target.resource, target.url, S.BLOCKED.value,
            not_attempted, None, round((time.perf_counter() - started) * 1000, 1),
            capability=target.capability,
            detail=f"egress proxy refused CONNECT ({exc}); policy denial and upstream "
                   "failure are indistinguishable from inside this environment",
        )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
        return ProbeResult(
            target.provider, target.resource, target.url, S.UNAVAILABLE.value,
            not_attempted, None, round((time.perf_counter() - started) * 1000, 1),
            capability=target.capability, detail=f"{type(exc).__name__}: {exc}",
        )
    finally:
        if owns:
            await client.aclose()

    latency = round((time.perf_counter() - started) * 1000, 1)
    state, auth_state, detail = classify_response(target, response, credential_present=bool(credential))
    quota = _quota_from_headers(response.headers)
    if target.provider == "api-football":
        try:
            quota.update(_api_football_body_quota(json.loads(response.content)))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return ProbeResult(
        target.provider, target.resource, target.url, state, auth_state, response.status_code,
        latency, quota=quota or {"exposed": False}, capability=target.capability, detail=detail,
        response_bytes=len(response.content),
    )


async def run_probes(
    session: AsyncSession | None,
    settings: Settings,
    targets: list[ProbeTarget] | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[ProbeResult]:
    results = [await probe_target(t, settings, client=client) for t in (targets or default_targets(settings))]
    if session is not None:
        for r in results:
            session.add(
                ProviderProbe(
                    provider=r.provider, resource=r.resource, endpoint=r.endpoint,
                    environment=settings.environment, state=r.state,
                    authentication_state=r.authentication_state, http_status=r.http_status,
                    latency_ms=r.latency_ms, quota=r.quota, capability=r.capability,
                    detail=r.detail, probed_at=datetime.fromisoformat(r.probed_at),
                )
            )
        await session.commit()
    return results


async def latest_probe_states(session: AsyncSession) -> dict[tuple[str, str], ProviderProbe]:
    """Most recent probe per (provider, resource). Absent = UNKNOWN."""
    rows = (await session.execute(select(ProviderProbe).order_by(ProviderProbe.probed_at.desc()))).scalars().all()
    latest: dict[tuple[str, str], ProviderProbe] = {}
    for row in rows:
        latest.setdefault((row.provider, row.resource), row)
    return latest


def provider_rollup(latest: dict[tuple[str, str], ProviderProbe]) -> dict[str, str]:
    """Provider-level state: AVAILABLE only if every probed resource is."""
    by_provider: dict[str, list[str]] = {}
    for (provider, _), row in latest.items():
        by_provider.setdefault(provider, []).append(row.state)
    out: dict[str, str] = {}
    for provider, states in by_provider.items():
        if all(s == S.AVAILABLE.value for s in states):
            out[provider] = S.AVAILABLE.value
        elif len(set(states)) == 1:
            out[provider] = states[0]
        else:
            out[provider] = "PARTIAL"
    return out
