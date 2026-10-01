"""Measured request latency per route (§32, §34).

Records every request's wall-clock latency and status against its route
template, so percentiles are computed from real requests served by this
process. Process-local; a multi-instance deployment needs an external
metrics backend (recorded as a limitation).
"""
from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.correlation import get_request_id

_SAMPLES: dict[str, deque] = defaultdict(lambda: deque(maxlen=20000))
_ERRORS: dict[str, int] = defaultdict(int)


class LatencyTelemetryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            key = f"{request.method} {getattr(route, 'path', request.url.path)}"
            _SAMPLES[key].append((time.perf_counter() - t0) * 1000)
            if status >= 500:
                _ERRORS[key] += 1


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return round(s[f] + (s[c] - s[f]) * (k - f), 2)


def latency_report(prefix: str | None = None) -> dict[str, Any]:
    out = {}
    for key, samples in _SAMPLES.items():
        if prefix and prefix not in key:
            continue
        vals = list(samples)
        out[key] = {"n": len(vals), "p50_ms": _pct(vals, 0.5), "p95_ms": _pct(vals, 0.95),
                    "p99_ms": _pct(vals, 0.99), "server_errors": _ERRORS.get(key, 0)}
    return {"source": "MEASURED_IN_PROCESS", "request_id": get_request_id(), "routes": out}


def reset() -> None:
    _SAMPLES.clear()
    _ERRORS.clear()
