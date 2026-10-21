# ADR-0004: Backend ownership and the gateway

Status: accepted (2026-10-11). Audit items: R14, N16.

## Context

Two FastAPI backends exist behind one frontend:

* `apps/api`: the analytics API (PostgreSQL; ingestion, canonical data, valuation, decision tooling).
* `Football_OS-frontend/backend`: an identity service (Google sign-in through the provider's session exchange; MongoDB
  sessions and per-user shortlists).

They defined overlapping routes (`/api/copilot/query`, `/api/status`, `/api/auth/me`) and the repository had no gateway
configuration, so which service answered depended on the deployment. The identity service also carried template leftovers:
an unauthenticated MongoDB write (`POST /api/status`), an ungrounded LLM "copilot" that answered football questions from
model memory (no data, no provenance) and a root message route.

## Decision

1. **Ownership is by URL prefix** and each URL has exactly one owner:

   | Prefix | Owner | Store |
   |---|---|---|
   | `/api/auth/*`, `/api/shortlists*` | identity service | MongoDB |
   | everything else under `/api/*` | analytics API | PostgreSQL |

2. `deploy/nginx.conf` implements that table. `tests/unit/test_gateway_ownership.py` fails if a URL is defined by both
   services, if the identity service defines anything outside its prefixes, if the gateway sends a prefix to the wrong
   owner, or if the frontend calls a path no backend serves.
3. The identity service's ungrounded LLM copilot, the `/api/status` template endpoints and the root route are **removed**.
   The copilot is the analytics API's data-grounded one (`POST /api/copilot/query`).
4. Authentication crosses the boundary through **short-lived bearer tokens** (HS256, <= 1 h, `jti` for revocation): the
   frontend signs in with the identity service, calls `POST /api/auth/token`, and sends the token to the analytics API.
   Key rotation uses `AUTH_JWT_SECRET_PREVIOUS`; revocation uses `POST /api/v1/admin/revocations`.

## Consequences

* Shortlists remain in MongoDB, which contradicts "PostgreSQL is the source of truth". **Target state:** a single backend
  with users, sessions and shortlists in PostgreSQL behind the same token contract. Until then the identity service is a
  separate deployable with its own secrets (`AUTH_JWT_SECRET`, `AUTH_ALLOWED_EMAILS`, `CORS_ORIGINS`).
* The revocation list is process-local (see `app/security/revocation.py`); a durable list is part of operational-state
  persistence.
* No Dockerfile or compose entry exists yet for the identity service or the gateway; add them with the first deployment.
* The gateway file is unverified until `nginx -t` and a smoke test have run in a real environment.
