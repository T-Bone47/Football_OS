# Decision Evidence Graph & Provenance Model (Phase 7)

## 1. Overview
In modern professional football intelligence, a recommendation without an audit trail is a liability. The Football Intelligence OS decision architecture grounds every recommendation, score, and scenario in an explicit **Decision Evidence Graph (DAG)**.

Scouts, sporting directors, and data analysts can inspect:
> *"What empirical evidence, feature distributions, model versions, and assumptions produced this specific candidate recommendation?"*

---

## 2. Evidence Graph Topology

Every evaluated candidate recommendation produces an immutable, directed acyclic graph:

```
                  ┌────────────────────────┐
                  │      Player Entity     │
                  └───────────┬────────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │ Contribution Snapshot  │
                  └───────────┬────────────┘
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
    ┌────────────────────┐        ┌────────────────────┐
    │    Role Profile    │        │  Peer Benchmarks   │
    └──────────┬─────────┘        └────────────────────┘
               │
         ┌─────┴───────────────┐
         ▼                     ▼
┌──────────────────┐  ┌──────────────────┐
│   Tactical Fit   │  │    Similarity    │
└────────┬─────────┘  └────────┬─────────┘
         │                     │
         └──────────┬──────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │ Transfer Comparables│
         └──────────┬──────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │ Valuation Baseline  │
         └──────────┬──────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │    Transfer Risk    │
         └──────────┬──────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │    Squad Scenario   │
         └──────────┬──────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │ Decision Assessment │
         └─────────────────────┘
```

---

## 3. Evidence Graph Data Model

### 3.1 Node Structure (`EvidenceGraphNode`)
```json
{
  "id": "node_unique_key",
  "node_type": "PLAYER | STATS | ROLE | TACTICAL | SIMILARITY | VALUATION | RISK | SQUAD | DECISION",
  "label": "Human-readable node label",
  "metric_value": 78.5,
  "confidence_score": 0.88,
  "provenance_source": "FastAPI canonical service / Model Registry",
  "as_of": "2026-09-25T22:00:00Z"
}
```

### 3.2 Edge Structure (`EvidenceGraphEdge`)
```json
{
  "source_node_id": "player_123",
  "target_node_id": "contrib_123",
  "relationship": "DERIVED_FROM | CONTRIBUTES_TO | CONSTRAINS | VALIDATES",
  "weight": 0.35,
  "is_hard_constraint": false
}
```

---

## 4. Explicit Data Sufficiency States

A decision cannot silently claim "high confidence" merely because multiple weak models agree. The engine outputs one of 5 mutually exclusive data sufficiency states:

| Status | Meaning | Criteria |
|---|---|---|
| `DECISION_AVAILABLE` | Full empirical evidence, validated models, within distribution. | Sample $\ge 1,200$ mins, all feature models active, OOD score $< 0.30$. |
| `LOW_CONFIDENCE` | Limited sample volume or elevated uncertainty interval. | Sample between $450$ and $1,200$ mins, or wide conformal valuation bounds. |
| `INSUFFICIENT_DATA` | Sample volume fails statistical significance threshold. | Sample $< 450$ mins or zero recorded season statistics. |
| `OUT_OF_DISTRIBUTION` | Candidate feature vector diverges from training distribution. | Target metrics exceed $3\sigma$ from training cohort means. |
| `PARTIAL_EVIDENCE` | One or more core analytical layers (e.g. transfer history) missing. | Historical transfer records unavailable or unverified league tier. |

Every status report contains explicit human-readable `uncertainty_drivers` explaining the limiting factor.
