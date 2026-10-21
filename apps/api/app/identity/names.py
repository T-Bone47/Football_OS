"""Name normalisation that preserves the original spelling.

The canonical `players.name` and every provider spelling are stored verbatim. These
helpers only produce a *comparison key* used for matching, so accents, Unicode and
transliterations still match while the display name is never rewritten.
"""
from __future__ import annotations

import re
import unicodedata

# Common football name particles and connectors that carry no identity signal.
_PARTICLES = {
    "da", "das", "dos", "de", "del", "della", "der", "di", "du", "la", "las", "le",
    "les", "el", "al", "bin", "ibn", "van", "von", "mac", "mc", "jr", "sr",
}

_PUNCTUATION = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WHITESPACE = re.compile(r"\s+", flags=re.UNICODE)


def strip_accents(value: str) -> str:
    """Fold diacritics for comparison only. The original string is never modified."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_name(name: str | None) -> str:
    """Return a comparison key: lower-cased, accent-folded, punctuation-free.

    "M. Akanji" -> "m akanji"; "Ángel Di María" -> "angel di maria".
    """
    if not name:
        return ""
    folded = strip_accents(str(name)).lower()
    folded = _PUNCTUATION.sub(" ", folded)
    folded = _WHITESPACE.sub(" ", folded).strip()
    return folded


def name_tokens(name: str | None) -> list[str]:
    """Tokens of the normalised name, minus particles."""
    return [token for token in normalize_name(name).split(" ") if token and token not in _PARTICLES]


def name_key(name: str | None) -> str:
    """A single comparison key: sorted significant tokens.

    Sorting makes "Akanji, Manuel" and "Manuel Akanji" comparable, and dropping
    particles makes "Di Maria" and "Maria" comparable at the surname level without
    ever equating two different players on the surname alone.
    """
    tokens = name_tokens(name)
    return " ".join(sorted(tokens))


def surname_key(name: str | None) -> str:
    tokens = name_tokens(name)
    return tokens[-1] if tokens else ""


def initials(name: str | None) -> str:
    tokens = name_tokens(name)
    if not tokens:
        return "?"
    return "".join(token[0] for token in tokens[:2]).upper()


def names_are_close(left: str | None, right: str | None) -> bool:
    """Cheap equality test on the comparison key (accent- and order-insensitive).

    Providers frequently abbreviate a given name ("M. Akanji" vs "Manuel
    Akanji"). A difference that consists only of expanded initials is treated as a
    close match; anything else is not.
    """
    left_key = name_key(left)
    right_key = name_key(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    left_tokens = left_key.split(" ")
    right_tokens = right_key.split(" ")
    left_set, right_set = set(left_tokens), set(right_tokens)

    def matches(token: str, candidate: str) -> bool:
        if token == candidate:
            return True
        # an abbreviation matches the full token it abbreviates (in either direction)
        if len(token) == 1 and candidate.startswith(token):
            return True
        return len(candidate) == 1 and token.startswith(candidate)

    left_ok = all(any(matches(token, candidate) for candidate in right_tokens) for token in left_tokens)
    right_ok = all(any(matches(token, candidate) for candidate in left_tokens) for token in right_tokens)
    return left_ok and right_ok
