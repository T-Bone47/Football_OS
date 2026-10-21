"""Canonical identity services: name normalisation and cross-provider resolution."""
from app.identity.names import (
    initials,
    name_key,
    name_tokens,
    names_are_close,
    normalize_name,
    surname_key,
)

__all__ = [
    "initials",
    "name_key",
    "name_tokens",
    "names_are_close",
    "normalize_name",
    "surname_key",
]
