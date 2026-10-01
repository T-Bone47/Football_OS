# Phase 16: Freshness Engine & Multi-Tier Dependency Propagation

## 1. Freshness Tiers & TTLs
The platform models data freshness across five connected architectural tiers:
- **RAW DATA**: TTL = 24h
- **CANONICAL DATA**: TTL = 24h
- **FEATURE STORE**: TTL = 48h
- **MODEL READINESS**: TTL = 168h (7 days)
- **DECISION RECORDS**: TTL = 336h (14 days)

## 2. Deterministic Staleness Propagation
Freshness is not evaluated in silos. The Freshness Engine builds a directed acyclic graph (DAG) of entity dependencies:
$$\text{Raw Feed} \longrightarrow \text{Canonical Entity} \longrightarrow \text{Features} \longrightarrow \text{Model Inference} \longrightarrow \text{Recruitment Decision}$$

When any upstream entity exceeds its TTL or is marked stale:
1. Downstream entities transition to `FreshnessState.STALE` or `FreshnessState.AGING`.
2. `requires_review` is set to `True` on dependent recruitment decisions.
3. The reason `UPSTREAM_DEPENDENCY_STALE` is added to `stale_reasons`.
4. Operational alerts are dispatched to recruitment decision makers.
