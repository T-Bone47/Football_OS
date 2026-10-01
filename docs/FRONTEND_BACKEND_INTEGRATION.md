# Football Intelligence OS — Frontend/Backend Integration Specification

## 1. Overview & Architectural Integrity

The **Football Intelligence OS** integration unites the Emergent React 19 frontend with the FastAPI and PostgreSQL backend into a unified, deterministic, production-grade intelligence workstation.

### Architecture Baseline
```
+-------------------------------------------------------------------------+
|                  Emergent React 19 Frontend (SPA)                       |
|   Tailwind CSS / Lucide / Recharts / Radix UI / Dynamic Dark Aesthetic  |
+-------------------------------------------------------------------------+
                                    │
                                    │ Axios (withCredentials: true, CORS)
                                    ▼
+-------------------------------------------------------------------------+
|                 Centralized API Layer (footballApi.js)                  |
|     Normalizes shapes while strictly preserving semantic truth          |
+-------------------------------------------------------------------------+
                                    │
                                    │ HTTP JSON REST (/api/v1/*, /api/*)
                                    ▼
+-------------------------------------------------------------------------+
|                    FastAPI Backend (Port 8000)                          |
|   Pydantic V2 Models • Clean Architecture Services • Temporal Cutoffs    |
+-------------------------------------------------------------------------+
                                    │
                                    │ SQLAlchemy 2.0 Async (asyncpg)
                                    ▼
+-------------------------------------------------------------------------+
|                     PostgreSQL Database (Port 5432)                     |
|  22 Tables • 9 Alembic Migrations • Provenance & Referential Integrity  |
+-------------------------------------------------------------------------+
```

---

## 2. Non-Negotiable Contract Guarantees

1. **PostgreSQL as Sole Database Engine**: No SQLite fallback is permitted or utilized in production or development.
2. **Zero Data Fabrication**: All entities, matches, lineups, statistics, features, and tactical scores originate from real PostgreSQL database records or mathematical models evaluated against real historical features.
3. **Semantic Distinction (NULL vs 0 vs INSUFFICIENT_DATA)**:
   - Unknown or absent metrics remain `null` / `—`.
   - Players with insufficient minutes (<600) strictly output `INSUFFICIENT_SAMPLE` or `INSUFFICIENT_DATA`.
   - Zero is reserved exclusively for observed zero counts (e.g. 0 yellow cards).
4. **Centralized API Communication**: Every frontend screen queries the backend exclusively via `src/lib/footballApi.js`.

---

## 3. End-to-End Route & Contract Matrix

| Frontend Route | API Function | Backend Endpoint | HTTP Method | Response Schema | Semantic Handling |
|---|---|---|---|---|---|
| `/` (Dashboard) | `getHealth`, `getClubs`, `getMatches`, `getPlayers` | `/health`, `/api/v1/clubs`, `/api/v1/matches`, `/api/v1/players` | `GET` | Health status + summary lists | Real entity counts; no mock KPI counts |
| `/players` | `getPlayers(params)` | `/api/v1/players` | `GET` | `list[PlayerSummaryResponse]` | Paginated canonical players |
| `/players/:id` | `getPlayer(id)` | `/api/v1/players/{id}` | `GET` | `PlayerDetailResponse` | Real bio, physicals, nationality |
| `/players/:id` (Features) | `getPlayerFeatures(id)` | `/api/v1/players/{id}/features` | `GET` | `PlayerFeatureSnapshotResponse` | 156+ feature snapshots per player |
| `/players/:id` (Role) | `getPlayerRole(id)` | `/api/v1/players/{id}/role` | `GET` | `RoleArchetypeResponse` | `INSUFFICIENT_SAMPLE` preserved when minutes < threshold |
| `/players/:id` (Profile) | `getPlayerRoleProfile(id)` | `/api/v1/players/{id}/role-profile` | `GET` | `RoleProfileResponse` | 9-dimension continuous role vector |
| `/players/:id` (Similar) | `getSimilarPlayers(id)` | `/api/v1/players/{id}/similar` | `GET` | `SimilarPlayersResponse` | Top-N cosine distance with `why_similar` |
| `/players/:id` (Tactical) | `getPlayerTacticalFit(id)` | `/api/v1/players/{id}/tactical-fit` | `GET` | `PlayerTacticalFitResponse` | Dimensional deficit & why_fit explanations |
| `/tactical/fit` | `getTacticalContexts()` | `/api/v1/tactical/contexts` | `GET` | `list[TacticalContextResponse]` | 17 standard tactical formations & roles |
| `/tactical/compare` | `compareTacticalFit(payload)`| `/api/v1/tactical-fit/compare` | `POST` | `TacticalFitComparisonResponse` | Head-to-head comparison with dimensional deltas |
| `/matches` | `getMatches(params)` | `/api/v1/matches` | `GET` | `list[MatchSummaryResponse]` | 1,154 canonical matches |
| `/matches/:id` | `getMatch(id)` | `/api/v1/matches/{id}` | `GET` | `MatchDetailResponse` | Flattened clubs with raw response intact |
| `/matches/:id` (Events) | `getMatchEvents(id)` | `/api/v1/matches/{id}/events` | `GET` | `list[MatchEventResponse]` | Real minute, type, player association |
| `/matches/:id` (Lineups) | `getMatchLineups(id)` | `/api/v1/matches/{id}/lineups` | `GET` | `list[MatchLineupResponse]` | Real starting XI, substitutes, formations |
| `/matches/:id` (Stats) | `getMatchStatistics(id)` | `/api/v1/matches/{id}/statistics` | `GET` | `list[MatchStatisticResponse]` | Comparative metrics (shots, passes, possession) |
| `/matches/:id` (Player Stats)| `getMatchPlayerStats(id)`| `/api/v1/matches/{id}/player-stats` | `GET` | `list[PlayerMatchStatResponse]` | Per-player individual match performance |
| Decision-Room Session | `getCurrentUser()`, `logout()` | `/api/auth/me`, `/api/auth/logout` | `GET`, `POST` | UserSession (`scout_01`) | No external OAuth dependencies |

---

## 4. State Machine Matrix & UI Resilience

All UI views render one of the 5 canonical state representations:
1. **Loading State**: Subtle animated skeleton loaders matching the dark analytical theme.
2. **Success State**: High-density tables, radar profiles, or match timelines powered by real PostgreSQL rows.
3. **Truthful Empty State**: Clear feedback when entities do not exist (e.g. `No match events recorded for this fixture`).
4. **Insufficient Sample State**: Explicit `INSUFFICIENT SAMPLE (<600 mins)` banner with muted indicators rather than fabricated `0%` scores.
5. **Backend Dependency / Error State**: Truthful system diagnostic alerting without crashing React or losing user navigation state.

---

## 5. Frozen Integration Baseline v1

The integration layer is now **FROZEN**. All future intelligence features (Valuation, Transfer Risk, Match Prediction, Squad Optimization) must enter through:

```
Canonical DB Model -> Feature Pipeline -> Decision Engine -> Pydantic Schema -> FastAPI Route -> footballApi.js -> UI Visualization
```
