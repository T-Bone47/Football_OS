# Football Intelligence OS — Transfer Market Expansion & Data Audit Report

**Phase**: 4.1B Transfer Market Data Expansion & Model Readiness  
**Date**: September 2026  
**Auditor**: Football Intelligence OS Data Engineering & Model Governance  

---

## 1. Transfer Universe Metrics

| Metric | Phase 4.1 Baseline | Phase 4.1B Expanded | Delta |
| :--- | :--- | :--- | :--- |
| **Total Transactions Ingested** | 52 | **97** | +45 (+86.5%) |
| **Merged Unique Transactions** | 52 | **95** | +43 (+82.7%) |
| **Qualified Transactions** | 37 | **78** | +41 (+110.8%) |
| **Usable Fee Targets (Supervised)** | 37 | **68** | +31 (+83.8%) |
| **Known Fees (`KNOWN_FEE`)** | 12 | **25** | +13 (+108.3%) |
| **Reported Fees (`REPORTED_FEE`)** | 25 | **43** | +18 (+72.0%) |
| **Estimated Fees (`ESTIMATED_FEE`)** | 0 | **0** | 0 (Strict policy) |
| **Unknown Fees (`UNKNOWN_FEE`)** | 15 | **17** | +2 |
| **Free Transfers (`FREE_TRANSFER`)** | 0 | **10** | +10 |
| **Loans (`is_loan = True`)** | 8 | **11** | +3 |

---

## 2. Entity Resolution & Identity Coverage

| Dimension | Count / Percentage | Target Threshold | Status |
| :--- | :--- | :--- | :--- |
| **Unique Transferred Players** | **55** | $\ge 100$ | **Deficit (-45)** |
| **Unique Clubs (Buying / Selling)** | **66** | $\ge 40$ | **SATISFIED** |
| **Unique Competitions Covered** | **5** (EPL, La Liga, Serie A, Bundesliga, Ligue 1) | $\ge 4$ | **SATISFIED** |
| **Unique Seasons** | **11** (2014/15 → 2023/24) | $\ge 5$ | **SATISFIED** |
| **Player Identity Resolution %** | **100.0%** | $\ge 98\%$ | **SATISFIED** |
| **Club Identity Resolution %** | **100.0%** | $\ge 95\%$ | **SATISFIED** |
| **Fee Reporting Coverage %** | **82.1%** | $\ge 60\%$ | **SATISFIED** |
| **Player Intelligence Coverage %** | **100.0%** | $\ge 40\%$ | **SATISFIED** |

---

## 3. Temporal Coverage & Span

- **Earliest Transfer**: `2014-07-01` (Toni Kroos, Bayern Munich → Real Madrid)
- **Latest Transfer**: `2024-02-02` (Winter Window 2024 additions)
- **Temporal Span**: **9 years, 7 months (10 seasons)**
- **Temporal Join Invariance**: Verified bit-for-bit identical under future data injection.

---

## 4. Subgroup Representation Breakdown

### 4.1 Position Cohorts
- **Goalkeepers (`GK`)**: 6 transactions (Threshold: 15) $\rightarrow$ **DEFICIT (-9)**
- **Defenders (`DEF`)**: 28 transactions (Threshold: 50) $\rightarrow$ **DEFICIT (-22)**
- **Midfielders (`MID`)**: 38 transactions (Threshold: 50) $\rightarrow$ **DEFICIT (-12)**
- **Attackers (`ATT`)**: 23 transactions (Threshold: 50) $\rightarrow$ **DEFICIT (-27)**

### 4.2 Fee Distribution Bands
- **< €10M**: 11 transactions
- **€10M – €30M**: 24 transactions
- **€30M – €70M**: 19 transactions
- **> €70M**: 14 transactions

### 4.3 Age Bands at Transfer
- **< 21 Years**: 14 transactions
- **21 – 24 Years**: 34 transactions
- **25 – 28 Years**: 36 transactions
- **29+ Years**: 11 transactions

---

## 5. Multi-Source Provenance & Deduplication Audit

- **Primary Source**: API-Football official endpoints (commercial subscription terms).
- **Secondary Benchmark Source**: Open Data Transfer Benchmark (CC0-1.0 Public Domain).
- **Deduplication Key**: Composite signature: `player_id::from_club::to_club::transfer_date::type`.
- **Duplicate Records Reconciled**: 2 overlapping records (Manuel Akanji and Jadon Sancho).
  - *Akanji*: Fees agree (€17.5M). Multi-source provenance preserved with 0 conflict.
  - *Sancho*: Primary reports €85.0M; secondary reports €80.0M (diff: 5.88% > 3% threshold). Resolved according to `PRIMARY_SOURCE_PRIORITY_NO_AVERAGING` preserving primary fee without synthetic averaging; conflict recorded in audit provenance.

---

## 6. Data Quality Tier Breakdown

- **HIGH Quality**: 68 records (Complete fee, full identity resolution, clean deal terms).
- **MEDIUM Quality**: 17 records (Undisclosed fee or secondary estimate excluded from modeling).
- **LOW Quality**: 10 records (Loan or free transfer with partial context).
- **Fabricated Records**: **0** (Strict anti-fabrication enforcement).
