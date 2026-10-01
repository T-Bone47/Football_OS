# Phase 16: Production Data Plane Architecture

## 1. Overview
The Production Data Plane is responsible for reliable, non-destructive, content-addressed ingestion across all supported providers (StatsBomb, Wyscout, Opta, Transfermarkt, API-Football) into Bronze, Silver, and Gold tiers.

## 2. Ingestion & Storage Invariants
1. **Bronze Immutable Snapshots**:
   - Content-addressed by deterministic SHA-256 fingerprint of the canonical JSON payload.
   - Raw ingested batches are preserved verbatim; updates never overwrite Bronze records.
2. **Strict Idempotency**:
   - Re-ingesting an identical batch produces the exact same SHA-256 digest.
   - Zero duplicate entities created (`records_added == 0`).
   - Re-confirmation is tracked as `records_updated` with refreshed timestamp and audit link.
3. **Silver Normalization**:
   - Normalizes pitch coordinates, match timestamps, player naming, and tactical formations.
   - Discrepancies between providers are tagged with `CONFLICT_DETECTED` and held for resolution rather than silently clobbering existing state.
4. **Gold Feature Store**:
   - Pre-aggregates rolling 90-minute metrics, tactical fit indicators, action values, and transfer market comparables.
   - Features carry strict version tags (`feature_version`) and timestamp boundaries.
