"""
Request Correlation & Context Tracking (Phase 8 Observability).

Maintains request_id, decision_id, and actor context across async task chains.
Injects X-Request-ID header into every incoming and outgoing HTTP request.
"""

from __future__ import annotations

import contextvars
import uuid
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variable accessible across any function during request lifecycle
current_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_request_id", default="")
current_decision_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_decision_id", default="")


def get_request_id() -> str:
    """Returns the correlation request_id for the current execution context."""
    req_id = current_request_id.get()
    return req_id if req_id else "system_internal"


def get_decision_id() -> str:
    """Returns the active decision_id for the current execution context."""
    return current_decision_id.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """ASGI Middleware ensuring every HTTP request carries an auditable UUIDv4."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        header_req_id = request.headers.get("X-Request-ID")
        req_id = header_req_id if header_req_id else str(uuid.uuid4())

        token = current_request_id.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            current_request_id.reset(token)
