# Phase 16: Copilot V6 Operational Intelligence Assistant

## 1. Operational Dispatcher Architecture
Copilot V6 transitions from an analytical assistant into an operational decision copilot. It routes natural language queries across 12 distinct operational query families:
1. `WHICH_MODELS_DEGRADED`: Inspects model serving latency, drift, and calibration.
2. `WHAT_BECAME_STALE`: Identifies data feeds, features, or decisions exceeding freshness TTLs.
3. `WHAT_CHANGED`: Summarizes recent provider updates, watchlist movements, and decision reviews.
4. `CAN_WE_TRUST_DECISION`: Validates epistemic status, evidence graph completeness, and freshness.
5. `WHICH_COMPETITIONS_READY`: Checks competition readiness gates for production serving.
6. `WHO_NEEDS_REVIEW`: Highlights players, decisions, or models flagged for review.
7. `SYSTEM_HEALTH_OVERVIEW`: Summarizes workers, cache hit ratios, and API health.
8. `AUDIT_EVENT_QUERY`: Searches cryptographically verified audit records.
9. `DATA_QUALITY_INCIDENTS`: Lists active and resolved ingestion quality incidents.
10. `WATCHLIST_STATUS`: Details watchlist item changes and recent evaluation evidence.
11. `BACKGROUND_JOB_STATUS`: Reports on running, queued, retrying, and failed jobs.
12. `GENERAL_OPERATIONS`: General operational telemetry guidance.

## 2. Epistemic Safety & Non-Causal Policy
Copilot responses strictly adhere to non-causal language guardrails:
- Correlation and statistical associations are explicitly framed as observational.
- Words such as "caused", "proves", or "guarantees" are strictly prohibited unless supported by counterfactual causal discovery with verified unconfoundedness.
- Prompt injection attempts are neutralized with structured telemetry outputs.
