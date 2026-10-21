"""Token revocation (token lifecycle policy).

Access tokens are short-lived (<= MAX_TOKEN_TTL_SECONDS) and are not refreshed: the identity service mints a new one
from the user's session. Revocation covers the gap until expiry:

* revoke_jti(jti)             a single stolen/leaked token
* revoke_subject(user, t)     everything issued to a user before t ("log out everywhere", incident response)

The list is PROCESS-LOCAL and in memory: it is lost on restart and not shared across workers. Because tokens expire
within an hour that bounds the exposure, but a durable, shared list is an open item (stage 3). Entries only need to
outlive the longest token, so prune() drops expired ones.
"""
from __future__ import annotations

import threading
import time

MAX_TOKEN_TTL_SECONDS = 3600
LEEWAY_SECONDS = 30


class RevocationList:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jtis: dict[str, int | None] = {}
        self._subjects: dict[str, int] = {}

    def revoke_jti(self, jti: str, expires_at: int | None = None) -> None:
        with self._lock:
            self._jtis[jti] = expires_at

    def revoke_subject(self, subject: str, not_before: int | None = None) -> None:
        with self._lock:
            self._subjects[subject] = int(time.time()) if not_before is None else not_before

    def is_revoked(self, jti: str, subject: str, issued_at: int) -> bool:
        with self._lock:
            return jti in self._jtis or (subject in self._subjects and issued_at < self._subjects[subject])

    def prune(self, now: int | None = None) -> int:
        now = int(time.time()) if now is None else now
        removed = 0
        with self._lock:
            for jti in [j for j, exp in self._jtis.items() if exp is not None and exp <= now]:
                del self._jtis[jti]
                removed += 1
            horizon = MAX_TOKEN_TTL_SECONDS + LEEWAY_SECONDS
            for subject in [s for s, nb in self._subjects.items() if nb + horizon <= now]:
                del self._subjects[subject]  # every token issued before not_before has expired by now
                removed += 1
        return removed


_GLOBAL: RevocationList | None = None


def get_revocations() -> RevocationList:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = RevocationList()
    return _GLOBAL
