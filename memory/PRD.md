# Football Intelligence OS — Frontend PRD

## Original problem statement
Design and implement a premium, production-quality frontend for the existing Football Intelligence OS analytics/scouting platform. It must consume the existing FastAPI/PostgreSQL/SQLAlchemy backend contracts (source of truth), never fabricate analytical data, and cover player intelligence, similarity, role discovery, market context, tactical fit, match intelligence, squad/scenario tools, AI Scout Copilot, provenance and data quality.

## Architecture
- Frontend: React 19 + CRA/craco, TanStack Query, React Router v7, Tailwind + shadcn/ui components, Recharts.
- Backend (pod): FastAPI on port 8001. Serves `/api/auth/*` and `/api/copilot/query` (streaming Claude Sonnet 5 via Emergent LLM key + emergentintegrations). Mongo used only for session store.
- External source of truth: Football_OS repo (`/app/Football_OS`) — canonical `/api/v1/*` contracts. Not mounted in the pod per user's decision; frontend renders graceful "backend dependency" states rather than fabricated data.

## Core personas
- Scout (player discovery, comparison, similarity, role fit)
- Analyst (feature evidence, model transparency, data quality)
- Recruitment lead (market context, replacements, valuation, risk)

## Core requirements (static)
- Never fabricate statistics, market values, predictions, or similarity scores.
- Every analytical output must have provenance (source, model version, snapshot).
- Distinguish FACT / MODEL OUTPUT / ESTIMATE with badges and copy.
- Dark, technical, calm design — semantic colour meaning (green/amber/red/purple).
- Responsive down to 390px without layout breakage.
- Command palette (⌘K) + AI Scout Copilot as primary decision surfaces.

## Implemented (2026-02)
- Application shell with sidebar (all groups: Overview / Intelligence / Recruitment / Match / Squad / Research / AI / System) + Cmd/Ctrl+K palette.
- Managed Google sign-in via Emergent (session cookie + `/api/auth/*`).
- Dashboard signals + status strip + decision-surface shortcuts.
- Player discovery (filters, sortable table, mobile-safe overflow).
- Player profile (metrics, role profile w/ evidence drawer, performance radar, similarity list, feature snapshot, valuation / tactical fit / transfer risk dependency cards).
- Player comparison (2–5 slots with picker).
- Similarity explorer (roster picker + multi-dimensional results with "why?" evidence drawer).
- Role discovery (clusters players by archetype from `/players/{id}/role`).
- Market intelligence (overview + valuation / opportunities / replacements / risk) with dependency states.
- Tactical fit workspace (player × club × formation × role, pitch preview + fit dimensions).
- Match intelligence (list + detail with events, lineups, stats, prediction dependency).
- Squad workspaces (builder / simulator / scenarios) with dependency states.
- Research lab (feature registry live; models/data/experiments dependency).
- Data quality (live canonical endpoint health check with pos/warn/risk badges).
- Scout Copilot (Claude Sonnet 5 SSE streaming, context injected from live players response, suggestion tiles).

## Backend dependencies (surfaced honestly in UI)
- `/api/v1/*` (Football_OS canonical) — not mounted in pod.
- Valuation, tactical fit scoring, transfer risk classification, market opportunity endpoints, replacement finder, squad construction, scenario simulator, match prediction, data quality summary — pending backend exposure.

## Prioritised backlog
- **P0**: Adapt Football_OS to a local SQLite/PostgreSQL runtime and mount `/api/v1/*` behind the pod so canonical data flows live.
- **P1**: Wire valuation / risk / tactical fit endpoints once backend exposes them.
- **P1**: Persist Copilot conversation history per user in Mongo.
- **P2**: Interactive pitch heatmaps once tactical feature vectors return heat data.
- **P2**: Command palette AI queries → auto-route to Copilot with detected criteria.
- **P2**: Saved shortlists + comparison presets.

## Next tasks
- Mount canonical backend (`Football_OS` API) or point `REACT_APP_BACKEND_URL` variant at an external base URL.
- Add valuation + risk cards to `PlayerProfilePage` once endpoints are live.
- Extend `PerformanceRadar` with reference-player overlay in comparison view.
