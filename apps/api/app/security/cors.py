"""CORS origin resolution (handoff §7.11 / R17): trusted origins only, never '*' with credentials."""
from __future__ import annotations

from urllib.parse import urlparse


def parse_cors_origins(raw: str) -> list[str]:
    """Parse a comma-separated origin list. Raises ValueError on a wildcard or malformed origin.

    The API sends credentialed responses, so a wildcard (or a regex that matches everything)
    would let any website read authenticated responses. Fail at startup instead.
    """
    origins: list[str] = []
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        if "*" in item:
            raise ValueError("CORS_ALLOWED_ORIGINS must list explicit origins; wildcards are not allowed with credentials")
        parsed = urlparse(item)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError(f"invalid CORS origin: {item!r} (expected scheme://host[:port])")
        origins.append(f"{parsed.scheme}://{parsed.netloc}")
    return list(dict.fromkeys(origins))
