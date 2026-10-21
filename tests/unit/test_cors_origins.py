"""CORS must name trusted origins; a wildcard with credentials is a startup error (R17)."""
from __future__ import annotations

import pytest

from app.security.cors import parse_cors_origins


def test_explicit_origins_normalised_and_deduplicated():
    raw = "http://localhost:3000, https://app.example.com/ ,http://localhost:3000"
    assert parse_cors_origins(raw) == ["http://localhost:3000", "https://app.example.com"]


@pytest.mark.parametrize("raw", ["*", "http://localhost:3000,*", "https://*.example.com"])
def test_wildcards_rejected(raw):
    with pytest.raises(ValueError):
        parse_cors_origins(raw)


@pytest.mark.parametrize("raw", ["localhost:3000", "ftp://x.com", "https://x.com/path", "https://x.com?q=1"])
def test_malformed_origins_rejected(raw):
    with pytest.raises(ValueError):
        parse_cors_origins(raw)


def test_empty_list_means_no_cross_origin_access():
    assert parse_cors_origins("") == []
