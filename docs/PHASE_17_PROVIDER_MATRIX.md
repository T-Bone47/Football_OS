# Phase 17 — Provider Connectivity and Capability Matrix

Evidence: `docs/evidence/phase17/live_pipeline.json` (`probes`, `capability_matrix`), `scheduler_run.json`, `load_test.json` (`provider_conditions`). Live endpoints: `GET /api/v1/ops/providers`, `POST /api/v1/ops/providers/probe`, `GET /api/v1/ops/capabilities`.

## 1. Connectivity (§3) — real probes, 2026-10-01

| Provider | Resource probed | State | Authentication | HTTP | Latency | Quota |
|---|---|---|---|---|---|---|
| StatsBomb Open Data | `competitions.json` | **AVAILABLE** | NOT_REQUIRED | 200 | 404 ms | not exposed by host |
| StatsBomb Open Data | `matches/43/106.json` | **AVAILABLE** | NOT_REQUIRED | 200 | 856 ms | not exposed |
| StatsBomb Open Data | `lineups/3869685.json` | **AVAILABLE** | NOT_REQUIRED | 200 | 2,026 ms | not exposed |
| API-Football | `/status` | **BLOCKED** | NOT_ATTEMPTED_KEY_PRESENT | – | 846 ms | unknown |
| football-data.org | `/competitions` | **BLOCKED** | NOT_ATTEMPTED_NO_KEY | – | 593 ms | unknown |

**API-Football.** The key is configured in the local, gitignored `.env`, is loaded, and is never printed or stored. The request never reaches API-Sports: this environment's egress proxy refuses the `CONNECT` to `v3.football.api-sports.io` before TLS (proxy record: `connect_rejected … gateway answered 403`). The key's validity, the plan quota and every API-Football capability are therefore **UNVERIFIED**. They are not `AUTH_FAILED`, which would claim the provider rejected the key. To verify, allow `v3.football.api-sports.io` in the environment's network settings and run `POST /api/v1/ops/providers/probe` or `tools/phase17/live_pipeline.py`. The probe then records the `/status` quota body (`response.requests.current/limit_day`) and `x-ratelimit-*` headers.

**football-data.org.** Blocked the same way; no token is configured. It also stays dormant by ADR-008.

**Classification rules** (`app/phase17/provider_probe.py`):

| Observed | State |
|---|---|
| Egress proxy refuses `CONNECT` | BLOCKED |
| DNS, TCP, TLS or timeout failure | UNAVAILABLE |
| 401/403, or an auth error inside a 200 envelope | AUTH_FAILED |
| 429 | RATE_LIMITED |
| 404 | CAPABILITY_UNAVAILABLE |
| 5xx | UNAVAILABLE |
| 2xx with usable JSON | AVAILABLE |

A provider with no probe row is UNKNOWN. A probe older than 24 h is reported UNKNOWN in system status.

Phase 16's orchestrator used to seed providers as `AVAILABLE` without making any request (reconnaissance R11). Its seeds are now `UNVERIFIED`.

## 2. Capability matrix (§4)

Dimensions: provider × competition × season × resource. `LIVE_AVAILABLE` means **verified by a real request from this deployment**. It does not mean real-time data.

### Provider × resource

| Resource | StatsBomb | API-Football | football-data.org |
|---|---|---|---|
| leagues / competitions | LIVE_AVAILABLE (index: 80 competition-seasons) | UNVERIFIED | UNVERIFIED |
| seasons | UNAVAILABLE (inside the index) | UNVERIFIED | UNAVAILABLE |
| fixtures / matches | LIVE_AVAILABLE (3 competition-seasons ingested) | UNVERIFIED | UNVERIFIED |
| teams | UNAVAILABLE (derived from matches) | UNVERIFIED | UNVERIFIED |
| players | UNAVAILABLE (derived from lineups) | UNVERIFIED | UNAVAILABLE |
| lineups | LIVE_AVAILABLE (478 matches) | UNVERIFIED | UNAVAILABLE |
| events | LIVE_AVAILABLE (24 matches) | UNVERIFIED | UNAVAILABLE |
| statistics | UNAVAILABLE | UNVERIFIED | UNAVAILABLE |
| transfers | UNAVAILABLE | UNVERIFIED | UNAVAILABLE |
| injuries | UNAVAILABLE | UNVERIFIED | UNAVAILABLE |
| standings | UNAVAILABLE | UNVERIFIED | UNVERIFIED |
| odds | UNAVAILABLE | UNVERIFIED (licensing not reviewed; not configured) | UNAVAILABLE |

UNAVAILABLE = the provider does not publish it. UNVERIFIED = it publishes it, but no request from here has succeeded.

### Competition × season (StatsBomb)

Of the 80 competition-seasons in the live StatsBomb index, **3 are LIVE_AVAILABLE** (ingested). The remaining 77 are **UNVERIFIED**: listed by the provider, never fetched.

| Competition | Season | Matches | Lineups | Events |
|---|---|---|---|---|
| Premier League (England) | 2015/2016 | 380 | 380 | 8 (sample) |
| FIFA World Cup (International) | 2022 | 64 | 64 | 8 (sample) |
| 1. Bundesliga (Germany) | 2023/2024 | 34 (Leverkusen only: **PARTIAL** league coverage) | 34 | 8 (sample) |

## 3. Provider behaviour under load and degradation (§32)

| Condition | Measured |
|---|---|
| Normal provider (StatsBomb lineups job through the API) | 670–764 ms, SUCCESS ×3 |
| Degraded provider (API-Football, blocked) | 2,465–2,628 ms (3 bounded adapter attempts), FAILED ×3, no fabricated payload |
| System status while a provider is degraded | 23.6 ms; reports DEGRADED with the provider BLOCKED |

## 4. What would change the matrix
- **Egress for `v3.football.api-sports.io` plus the configured key**: API-Football rows move from UNVERIFIED to AVAILABLE or AUTH_FAILED, and quota becomes PROVIDER_REPORTED. Fixtures could then be LIVE scheduled, the only source here that could support near-live match state.
- **Expanding StatsBomb scope**: another competition-season becomes LIVE_AVAILABLE only after its own ingestion run. Nothing is inherited.
