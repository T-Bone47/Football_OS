"""Structured Logging & Telemetry Engine (Phase 8 Observability).

Enforces:
- Structured JSON log emission
- Contextual correlation: request_id, decision_id, model_version, calculation_version
- Secret & sensitive information redaction (passwords, tokens, API keys)
- Clean integration with Starlette / FastAPI middleware
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

from app.observability.correlation import get_decision_id, get_request_id

# Regex patterns for sensitive key/token redaction
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|bearer|authorization|token)['\"]?\s*[:=]\s*['\"]?([^'\"\s,]+)"),
]

REDACTED_TEXT = "[REDACTED]"


def redact_sensitive_str(message: str) -> str:
    """Scans and redacts API keys, passwords, and authorization tokens from text."""
    redacted = message
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(r"\1=" + REDACTED_TEXT, redacted)
    return redacted


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as auditable single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = get_request_id()
        dec_id = get_decision_id()

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_str(record.getMessage()),
            "request_id": req_id,
        }

        if dec_id:
            payload["decision_id"] = dec_id

        # Merge extra attributes if passed
        if hasattr(record, "model_version"):
            payload["model_version"] = getattr(record, "model_version")
        if hasattr(record, "calculation_version"):
            payload["calculation_version"] = getattr(record, "calculation_version")
        if hasattr(record, "scenario_id"):
            payload["scenario_id"] = str(getattr(record, "scenario_id"))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Configures the root and app loggers with JSON formatting."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Returns a namespaced structured logger."""
    return logging.getLogger(name)
