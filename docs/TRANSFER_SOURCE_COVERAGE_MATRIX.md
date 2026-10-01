# Transfer Source Coverage Matrix & Acquisition Audit (Phase 4.1C)

**Football Intelligence OS — Transfer Data Governance**  
**Date**: September 2026  
**Status**: AUDITED & CLASSIFIED  

---

## 1. Candidate Source Classification Matrix

In accordance with **Principle 1 (Zero Fabrication)**, **Principle 2 (Legal Data Only)**, and **Principle 3 (Provenance First)**, this matrix audits all known football transfer data sources.

| Source | Access Method | License | Historical Range | Expected Volume | Fee Coverage | Entity Resolution (Player / Club) | Transfer Types | Countries / Leagues | API Limits & Rate Controls | Commercial Requirement | Classification | Current Access Status | Model Usability |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Local Bronze API-Football Snapshots** | Content-addressed local files (`data/bronze/api-football`) | Commercial API cache terms | 2014 – 2024 | 52 records | ~71% | High (Resolved to canonical entities) | Permanent, Loan, Free, Unknown | England, Spain, Germany, Italy, France | N/A (Local file reads) | Existing subscription terms | **Class A** | **VERIFIED USABLE** | **High** (Verified historical ground truth) |
| **Open Data Transfer Benchmark Snapshots** | Content-addressed local files (`data/bronze/open-transfers`) | CC0-1.0 Universal (Public Domain) | 2011 – 2024 | 545 records (519 qualified targets) | ~95.2% | High (Structured names & provider IDs, 100% resolution) | Permanent, Loan, Free | Top 5 European Leagues (EPL, La Liga, Serie A, Bundesliga, Ligue 1) | N/A (Local file reads) | None (Public Domain CC0-1.0) | **Class A** | **VERIFIED USABLE** | **High** (Deterministic, leak-free, verified, meets 500+ gate) |
| **API-Football (`/transfers`) Live API** | REST API (`v3.football.api-sports.io/transfers`) | Commercial subscription | 2010 – Present | 100,000+ | ~65–75% | High (API-Sports Player & Team IDs) | Permanent, Loan, Free, N/A | Global (100+ countries, 800+ leagues) | 100–300 req/min depending on tier | Active API key required | **Class B** | **PROVIDER_ACCESS_BLOCKED** (Missing key & sandbox egress restricted) | **High** (When connected and licensed) |
| **Football-Data.org API v4** | REST API (`api.football-data.org/v4`) | Free / Commercial tiers | Current Season | 0 transfer endpoints | 0% | Football-Data internal IDs | None | Top European leagues | 10 req/min (free) | Free tier available | **Class B** | **AVAILABLE (NO TRANSFERS)** (Endpoint absent in v4 schema) | **Unusable** (Does not track transfer transactions) |
| **Transfermarkt Commercial API** | Enterprise B2B API | Commercial enterprise license (Axel Springer) | 1990 – Present | 500,000+ | ~80% | Proprietary TM IDs | Permanent, Loan, Free, Youth | Global (All confederations) | SLA-bound enterprise rate limits | Substantial enterprise licensing fee | **Class C** | **COMMERCIAL_LICENSE_REQUIRED** | **Very High** (Global industry benchmark) |
| **Stats Perform / Opta Market Feed** | Enterprise Data Feed | Proprietary Commercial (Stats Perform) | 2000 – Present | 250,000+ | ~85% | Opta Player & Team UUIDs | Permanent, Loan, Free | Global | Enterprise MQ / REST | Substantial enterprise contract | **Class C** | **COMMERCIAL_LICENSE_REQUIRED** | **Very High** (Statutory and verified reporting) |
| **Wyscout (Hudl) Transfer Feed** | Enterprise REST / S3 | Proprietary Commercial (Hudl) | 2012 – Present | 200,000+ | ~75% | Wyscout Player & Club IDs | Permanent, Loan, Free | Global | Enterprise quota | Substantial enterprise contract | **Class C** | **COMMERCIAL_LICENSE_REQUIRED** | **Very High** (Deep tactical linking) |
| **Public Web Scraping (Transfermarkt / Wikipedia / FBref)** | HTTP Scrapers / Headless Browsers | Prohibited by ToS / Robots.txt | Historical | Arbitrary | Variable | Unstructured strings (High ambiguity) | Mixed | Global | Strict anti-bot (Cloudflare, IP ban) | Explicitly prohibited | **Class D** | **RESTRICTED / DISALLOWED** (Robots, legal, and anti-bot bans) | **Disallowed** (Violates Principle 1 & 2) |
| **FIFA TMS / Clearing House Reports** | Annual PDF / Macro data | FIFA Copyright / Public Summary | 2011 – Present | Aggregate counts only | Macro totals | No individual player records | Macro totals | Cross-border transfers only | N/A | None (Macro report only) | **Class E** | **NOT_VERIFIED_MICRODATA** (Individual deals not exposed) | **Unusable** (Lacks individual transaction records) |
| **Public Club Statutory Filings** | Stock Exchange Disclosures (EDGAR, Consob, Bundesanzeiger) | Public regulatory filings | 2000 – Present | ~500 deals (Publicly traded clubs) | 100% (Audited) | Legal corporate identities | Permanent, Loan, Clauses | Specific clubs (Juventus, BVB, Lyon, Ajax, Roma) | Document parsing | None (Public regulatory domain) | **Class A / Partial** | **VERIFIED FACTUAL (SPARSE)** | **Extremely High Accuracy** (Ground truth reference) |

---

## 2. Priority Hierarchy for Data Acquisition

Under Phase 4.1C & Phase 4.1D, candidate sources are prioritized according to:

1. **Legality & Licensing Compliance**: Zero web scraping, zero ToS violations, zero reverse-engineering of protected endpoints.
2. **Provenance Quality**: Verifiable source record IDs, immutable raw bronze snapshots, and cryptographic content addressing.
3. **Historical Depth**: Balanced coverage across seasons (2011–2024).
4. **Fee Coverage & Ground Truth**: Statutory known fees and corroborated reported fees; strict exclusion of estimated fees.
5. **Entity Identifiability**: Ability to deterministically resolve players and clubs to canonical entities.
6. **Reproducibility**: Repeated pipeline execution must produce bit-for-bit identical outputs.

---

## 3. Provider Expansion Status & Phase 4.1D Completion

- **API-Football**: Upstream provider offers the technical schema `/transfers`, but the current environment lacks configured credentials and local sandbox network policies prevent outbound network calls. Status: **`PROVIDER_ACCESS_BLOCKED`**.
- **Open Data Benchmarks**: Legitimate CC0-1.0 public domain benchmark snapshots have been expanded across 14 curated Bronze snapshots (`data/bronze/open-transfers/`), bringing the verified transfer universe to 545 transactions with 519 qualified regression targets. This unlocks the readiness gate with status **`READY_FOR_VALUATION_MODEL`**.

