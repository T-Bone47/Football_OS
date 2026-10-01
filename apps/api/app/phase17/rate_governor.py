"""Measured provider rate-limit governance (§8).

Budgets come from one of three sources, and the source is always reported:
- PROVIDER_REPORTED: read from the provider's own quota response (e.g. the
  API-Football /status body) during a probe.
- SELF_IMPOSED: the provider documents no quota for this host (StatsBomb
  Open Data is served by raw.githubusercontent.com); we cap ourselves.
- CONSERVATIVE_DEFAULT_UNVERIFIED: the provider has a quota we could not
  read; the cap is deliberately low and labelled unverified.

Every HTTP attempt — including tenacity retries inside the adapters — goes
through `instrumented_client()`'s event hooks, so requests/minute,
requests/hour, 429s and retries are counted, not estimated.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ProviderBudget:
    provider: str
    per_minute: int
    per_hour: int | None
    source: str


DEFAULT_BUDGETS: dict[str, ProviderBudget] = {
    "statsbomb": ProviderBudget("statsbomb", per_minute=60, per_hour=2000, source="SELF_IMPOSED"),
    "api-football": ProviderBudget("api-football", per_minute=10, per_hour=100,
                                   source="CONSERVATIVE_DEFAULT_UNVERIFIED"),
    "football-data-org": ProviderBudget("football-data-org", per_minute=10, per_hour=None,
                                        source="CONSERVATIVE_DEFAULT_UNVERIFIED"),
}


@dataclass
class ProviderUsage:
    request_times: deque = field(default_factory=deque)
    total_requests: int = 0
    http_429: int = 0
    http_5xx: int = 0
    transport_errors: int = 0
    logical_fetches: int = 0
    backoff_seconds: float = 0.0
    deferred: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    cooldown_until: float = 0.0

    @property
    def retries(self) -> int:
        return max(0, self.total_requests - self.logical_fetches)


class RateGovernor:
    """Process-local sliding-window governor. Multi-worker deployments need
    a shared store; that is recorded as a limitation, not hidden."""

    backend = "PROCESS_LOCAL"

    def __init__(self, budgets: dict[str, ProviderBudget] | None = None, clock=time.monotonic) -> None:
        self._budgets = dict(budgets or DEFAULT_BUDGETS)
        self._usage: dict[str, ProviderUsage] = {}
        self._clock = clock

    def budget(self, provider: str) -> ProviderBudget:
        return self._budgets.get(provider) or ProviderBudget(provider, 5, 50, "CONSERVATIVE_DEFAULT_UNVERIFIED")

    def set_budget(self, budget: ProviderBudget) -> None:
        self._budgets[budget.provider] = budget

    def usage(self, provider: str) -> ProviderUsage:
        return self._usage.setdefault(provider, ProviderUsage())

    def _trim(self, u: ProviderUsage, now: float) -> None:
        while u.request_times and now - u.request_times[0] > 3600:
            u.request_times.popleft()

    def window_counts(self, provider: str) -> tuple[int, int]:
        u = self.usage(provider)
        now = self._clock()
        self._trim(u, now)
        last_min = sum(1 for t in u.request_times if now - t <= 60)
        return last_min, len(u.request_times)

    def record_rate_limited(self, provider: str, retry_after_s: float = 60.0) -> None:
        """The provider itself said 429 (after the adapter's bounded retries).
        Our own budget is irrelevant now: nothing is sent until the cooldown
        ends."""
        u = self.usage(provider)
        u.cooldown_until = max(u.cooldown_until, self._clock() + retry_after_s)

    def headroom(self, provider: str, needed: int = 1) -> bool:
        if self._clock() < self.usage(provider).cooldown_until:
            return False
        b = self.budget(provider)
        per_min, per_hour = self.window_counts(provider)
        if per_min + needed > b.per_minute:
            return False
        if b.per_hour is not None and per_hour + needed > b.per_hour:
            return False
        return True

    def seconds_until_headroom(self, provider: str) -> float:
        u = self.usage(provider)
        now = self._clock()
        recent = [t for t in u.request_times if now - t <= 60]
        if len(recent) < self.budget(provider).per_minute:
            return 0.0
        return max(0.0, 60 - (now - recent[0]))

    def record_request(self, provider: str, status: int | None, latency_ms: float | None) -> None:
        u = self.usage(provider)
        u.request_times.append(self._clock())
        u.total_requests += 1
        if latency_ms is not None:
            u.latencies_ms.append(latency_ms)
        if status == 429:
            u.http_429 += 1
        elif status is not None and status >= 500:
            u.http_5xx += 1
        elif status is None:
            u.transport_errors += 1

    def record_fetch(self, provider: str) -> None:
        self.usage(provider).logical_fetches += 1

    def record_deferral(self, provider: str, waited_s: float = 0.0) -> None:
        u = self.usage(provider)
        u.deferred += 1
        u.backoff_seconds += waited_s

    def report(self) -> dict[str, Any]:
        out: dict[str, Any] = {"backend": self.backend, "providers": {}}
        for provider, u in self._usage.items():
            per_min, per_hour = self.window_counts(provider)
            b = self.budget(provider)
            out["providers"][provider] = {
                "budget": {"per_minute": b.per_minute, "per_hour": b.per_hour, "source": b.source},
                "requests_last_minute": per_min,
                "requests_last_hour": per_hour,
                "total_requests": u.total_requests,
                "logical_fetches": u.logical_fetches,
                "retries": u.retries,
                "http_429": u.http_429,
                "http_5xx": u.http_5xx,
                "transport_errors": u.transport_errors,
                "deferred_for_budget": u.deferred,
                "backoff_seconds": round(u.backoff_seconds, 2),
                "budget_exceeded": per_min > b.per_minute or (b.per_hour is not None and per_hour > b.per_hour),
                "in_provider_cooldown": self._clock() < u.cooldown_until,
            }
        return out


def instrumented_client(governor: RateGovernor, provider: str, timeout: float = 30.0,
                        transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    starts: dict[int, float] = {}

    async def on_request(request: httpx.Request) -> None:
        starts[id(request)] = time.perf_counter()

    async def on_response(response: httpx.Response) -> None:
        started = starts.pop(id(response.request), None)
        latency = (time.perf_counter() - started) * 1000 if started else None
        governor.record_request(provider, response.status_code, latency)

    kwargs: dict[str, Any] = {"timeout": timeout, "event_hooks": {"request": [on_request], "response": [on_response]}}
    if transport is not None:
        kwargs["transport"] = transport
    return httpx.AsyncClient(**kwargs)


_GOVERNOR: RateGovernor | None = None


def get_rate_governor() -> RateGovernor:
    global _GOVERNOR
    if _GOVERNOR is None:
        _GOVERNOR = RateGovernor()
    return _GOVERNOR
