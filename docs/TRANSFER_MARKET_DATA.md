# Transfer Market Data Foundation (Phase 4.1)

## 1. Overview & Architectural Role

The Transfer Market Intelligence & Valuation Data Foundation provides the verified historical transaction layer for Football Intelligence OS. Its primary mission is to establish a rigorous, defensible, and leakage-safe data universe before any statistical or machine-learning valuation models are deployed.

In strict compliance with **Non-Negotiable Principle 1 (Zero Fabrication)** and **Principle 6 (Data Sufficiency Hard Gate)**, this system:
1. Reconstructs transactions exclusively from verified bronze source snapshots.
2. Distinguishes confirmed/reported deals from undisclosed, free, and loan agreements.
3. Maps provider player and club identities to canonical entities without heuristic guesswork.
4. Enforces bit-for-bit temporal invariance for all historical evaluations as of cutoff date $T$.
5. Implements a transparent multi-dimensional comparable engine and deterministic baseline valuation engine.

---

## 2. Canonical Transfer Entity Schema

The canonical `Transfer` entity is persisted in PostgreSQL (Alembic migration `0012_canonical_transfers_and_market.py`) and is mapped to existing canonical `Player`, `Club`, and `Season` models:

```sql
CREATE TABLE transfers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    from_club_id UUID REFERENCES clubs(id) ON DELETE SET NULL,
    to_club_id UUID REFERENCES clubs(id) ON DELETE SET NULL,
    transfer_date DATE,
    season_id UUID REFERENCES seasons(id) ON DELETE SET NULL,
    competition_context VARCHAR(100),
    transfer_type VARCHAR(50) NOT NULL,
    fee_value NUMERIC(14, 2),
    fee_currency VARCHAR(10),
    fee_status VARCHAR(50) NOT NULL,
    fee_eur_normalized NUMERIC(14, 2),
    fee_min NUMERIC(14, 2),
    fee_max NUMERIC(14, 2),
    is_loan BOOLEAN NOT NULL DEFAULT FALSE,
    is_permanent BOOLEAN NOT NULL DEFAULT TRUE,
    option_type VARCHAR(50) NOT NULL DEFAULT 'NONE',
    source_provider VARCHAR(50) NOT NULL,
    source_record_id VARCHAR(100) NOT NULL UNIQUE,
    source_snapshot_id UUID REFERENCES data_snapshots(id) ON DELETE SET NULL,
    ingestion_run_id UUID REFERENCES ingestion_runs(id) ON DELETE SET NULL,
    normalization_version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    data_quality_status VARCHAR(30) NOT NULL DEFAULT 'MEDIUM',
    quality_reasons JSONB DEFAULT '[]'::jsonb,
    raw_data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_transfers_player_date ON transfers(player_id, transfer_date);
CREATE INDEX idx_transfers_date_fee ON transfers(transfer_date, fee_eur_normalized);
CREATE INDEX idx_transfers_to_club ON transfers(to_club_id);
CREATE INDEX idx_transfers_from_club ON transfers(from_club_id);
```

---

## 3. Controlled Fee Taxonomy & Semantics

Transfer fee metadata enforces the controlled taxonomy defined in `app.market.taxonomy`:

| Fee Status | Semantic Definition | Usable for Modeling? | Default `fee_eur_normalized` |
|---|---|---|---|
| `KNOWN_FEE` | Officially confirmed via club statutory disclosure / exchange filing. | Yes | Verified amount |
| `REPORTED_FEE` | Reported by reliable journalistic sources / provider consensus. | Yes | Verified amount |
| `ESTIMATED_FEE` | Source explicitly tags fee as an estimate / market value proxy. | Flagged (Sensitivity testing only) | Estimated amount |
| `FREE_TRANSFER` | Contract expiry, release, or mutual termination with zero acquisition fee. | Yes (Categorical cohort only) | `0.00` |
| `UNKNOWN_FEE` | Transaction occurred but fee was undisclosed or unrecorded. | **No (Strictly withheld)** | `None` |
| `UNDISCLOSED` | Clubs explicitly agreed to withhold financial terms. | **No (Strictly withheld)** | `None` |
| `LOAN` | Temporary sporting registration transfer; fee reflects loan stipend. | Sub-model only | Loan fee or `None` |
| `LOAN_WITH_OPTION` | Loan agreement with non-mandatory purchase option. | Sub-model only | Loan fee or `None` |
| `LOAN_WITH_OBLIGATION` | Loan agreement with mandatory future purchase obligation. | Future permanent fee cohort | Obligation amount |

### The "Unknown Is Not Zero" Mandate
In accordance with Non-Negotiable Principle 7:
- `UNKNOWN_FEE` $\neq$ `FREE_TRANSFER`
- `UNDISCLOSED` $\neq$ `€0`
- Under no circumstances does the frontend or analytical engine coerce an unknown or undisclosed fee to `€0`.

---

## 4. Multi-Dimensional Comparable Engine

The `ComparableTransferEngine` (`app.market.comparables`) retrieves historical permanent transfers strictly occurring on or before evaluation date $T$, matching against the target player's role, age, contribution profile, and league tier:

$$S = 0.30 \cdot S_{\text{role}} + 0.25 \cdot S_{\text{contrib}} + 0.20 \cdot S_{\text{age}} + 0.15 \cdot S_{\text{tier}} + 0.10 \cdot S_{\text{recency}}$$

- **Outfield vs. Goalkeeper Isolation**: Hard gate prevents outfield players from matching against goalkeepers.
- **Recency Decay**: Transactions decay with a 5-year half-life ($\lambda = 0.15$), reflecting football market inflation.
- **Output Transparency**: Every comparable transfer includes its individual dimensional similarity breakdown (`role`, `age`, `contribution`, `tier`, `recency`).

---

## 5. Deterministic Baseline Valuation Engine

Before training any complex ML model, the system computes a deterministic reference baseline (`BaselineValuationEngine`):

$$\hat{V}_{\text{baseline}} = \text{Median}\left(\{F_i^{\text{EUR}} \mid i \in \text{Top-10 Comps}\}\right) \times \gamma(\text{Age})$$

### Empirical Age Curve Multipliers $\gamma(\text{Age})$:
- $< 21.0$ years: $\times 1.15$ (Developmental upside premium)
- $21.0 - 24.0$ years: $\times 1.10$ (Pre-peak appreciation)
- $24.0 - 28.5$ years: $\times 1.00$ (Peak career maturity)
- $28.5 - 31.0$ years: $\times 0.85$ (Contract amortization discount)
- $> 31.0$ years: $\times 0.65$ (Veteran depreciation)

### Sample Sufficiency & Uncertainty Ranges
- If $n < 3$ usable comparable transfers: Returns `VALUATION_UNAVAILABLE` (Status: `INSUFFICIENT_DATA`).
- If $3 \le n < 5$: Point baseline is calculated, but uncertainty bounds return `RANGE_NOT_AVAILABLE`.
- If $n \ge 5$: Interquartile range ($[Q_1 \times \gamma, Q_3 \times \gamma]$) is provided as an empirical 50% dispersion interval.

---

## 6. Temporal Safety & Leakage Prevention

To guarantee strict temporal validity:
1. Every transfer query accepts an optional `as_of` timestamp.
2. The database query enforces `Transfer.transfer_date <= as_of.date()`.
3. In-memory snapshots enforce `filter_transfers_in_memory_as_of`.
4. Automated tests verify that injecting future transactions ($T + \Delta t$) leaves the historical dataset as of $T$ **bit-for-bit identical**.

---

## 7. Status & Readiness for Phase 4.2

As established by the Market Coverage Audit, the current verified transaction volume is:
- Total transactions: 52
- Qualified permanent fee transactions: 37
- Required for non-linear ML training (XGBoost/LightGBM): $\ge 500$ across multiple leagues.

**Hard Gate Assessment**: `INSUFFICIENT_TRANSFER_DATA`.
ML training is strictly gated until large-scale commercial/licensed transfer feeds are ingested.
