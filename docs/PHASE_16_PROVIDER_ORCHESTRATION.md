# Phase 16: Provider Orchestration, Rate-Limiting & Failover

## 1. Provider Capabilities
The platform maintains explicit capability profiles for each external data provider across supported resource types:
- **StatsBomb**: Event data, high-resolution 360 frames, match lineups.
- **Wyscout**: Player actions, team shapes, international coverage.
- **Opta**: Live match events, official match results, tournament metadata.
- **Transfermarkt**: Market valuations, transfer history, contract expiration dates.
- **API-Football**: Live match fixtures, standings, team rosters.

## 2. Rate Limiting & Token Bucket Governance
- Per-minute rate limits are tracked in real-time (`rate_limit_per_minute`).
- Calls exceeding allowances transition provider capability status to `RATE_LIMITED`.
- Automatic backoff prevents provider IP blocking or quota exhaustion.

## 3. Controlled Failover
- In the event of network timeouts, HTTP 5xx responses, or provider unavailability, the system executes controlled failover to secondary providers.
- Failover records carry explicit provenance markers (`failover_occurred=True`, `resolved_provider`).
- If providers disagree on critical scalar fields (e.g. match score 2-1 vs 1-1), `detect_conflicts()` emits `CONFLICT_DETECTED` and flags the record for manual scout review without silent overwrite.
