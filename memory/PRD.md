# Football Intelligence OS — Product Requirements

## Original Problem Statement

Build a premium, production-quality frontend for Football Intelligence OS, a professional football analytics, scouting, recruitment, tactical analysis, market intelligence, and decision-intelligence platform. Preserve the existing backend as the source of truth, consume its APIs rather than inventing analytics, provide clear provenance and uncertainty, and use graceful `DATA NOT AVAILABLE`, `INSUFFICIENT DATA`, or `BACKEND DEPENDENCY` states when capabilities are not connected. The interface should feel technical, calm, precise, dense, trustworthy, responsive, accessible, and unlike a generic SaaS or AI dashboard. Required areas include the application shell, dashboard, player intelligence, comparison/similarity, market, tactical fit, matches, squad/scenario tools, research, Scout Copilot, data provenance, model transparency, and data quality.

The related requested feature is Emergent managed Google sign-in added to the login screen while preserving compatible existing session behavior.

## Architecture Decisions

- React frontend with React Router, TanStack Query already available, Lucide icons, and centralized CSS tokens.
- FastAPI remains the backend and MongoDB remains the configured data store.
- Managed Google OAuth is exchanged server-side through the Emergent session-data endpoint.
- Sessions use a custom UUID-style `user_id`, a seven-day HTTP-only secure cookie, `/api/auth/me`, and `/api/auth/logout`.
- Frontend API requests use `REACT_APP_BACKEND_URL`; MongoDB uses the existing `MONGO_URL` and `DB_NAME`.
- Analytics are never fabricated. Unconnected screens explicitly identify backend dependencies.

## User Personas

- Recruitment director evaluating player value, risk, and alternatives.
- Scout investigating role fit, similarity, and evidence.
- Performance analyst comparing tactical and statistical outputs.
- Technical decision-maker reviewing market, squad, and scenario intelligence.

## Core Requirements (Static)

- Persistent desktop sidebar and professional command/workspace surfaces.
- Player discovery, similarity, market, transfer risk, tactical fit, match center, research, and Scout Copilot routes.
- Clear hierarchy between decision information, supporting evidence, and technical metadata.
- Responsive behavior for desktop, tablet, and mobile without horizontal overflow.
- Loading, empty, error, unavailable, partial-data, and backend-dependency states.
- Accessible labels, keyboard-friendly controls, visible focus, and descriptive test IDs.
- Managed Google sign-in from the login screen with server-verified sessions.

## Implemented — 2026-09-20

- Added managed Google login button using a dynamic current-origin redirect.
- Added server-side OAuth session exchange, provider payload validation, secure cookie storage, `/api/auth/me`, and logout.
- Added protected routing with synchronous hash callback detection and server-side auth verification.
- Replaced the starter splash with a football intelligence login experience.
- Added application shell with sidebar navigation and dashboard session status.
- Added workspace routes for players, similarity, market, transfer risk, tactical fit, matches, research, and Scout Copilot.
- Added explicit backend dependency states instead of fake analytical values.
- Added responsive styling and production build verification.
- Added `/app/auth_testing.md` and live auth regression coverage.

## Backend Dependencies / Known Limitations

- Player statistics, valuation, similarity, tactical fit, match, squad, model, data quality, and copilot data are not exposed by the current starter backend, so their UI currently shows a truthful backend dependency state.
- Real Google provider consent requires an operator-supplied Google identity and was not completed during automated testing; the session contract and invalid callback handling were verified.
- Existing backend CORS configuration remains wildcard-compatible through origin regex for credentialed requests; production origin restriction should be aligned with the connected deployment domain.

## Prioritized Backlog

### P0

- Map the existing Football Intelligence OS API contracts into typed frontend query hooks.
- Replace workspace dependency states with real player, market, match, tactical, and provenance data where endpoints exist.
- Add real profile, comparison, and evidence drawer flows.

### P1

- Add command palette search with Cmd/Ctrl+K.
- Add configurable analytical tables, filters, column density, and mobile transformations.
- Add provenance and model transparency components backed by API metadata.
- Add squad builder, transfer simulator, and scenario lab once backend contracts are available.

### P2

- Add chart visualizations, pitch views, embedding maps, and virtualized large tables.
- Add data quality, ingestion, models, experiments, and reports pages.
- Add richer account menu and session expiry handling.

## Next Tasks

1. Connect the real repository or API contract source and inventory its routes.
2. Create a typed API client and TanStack Query hooks for available endpoints.
3. Build the player search/profile flow first, then reuse its evidence components across market and tactical views.
4. Add the command palette and provenance drawer after real data is connected.