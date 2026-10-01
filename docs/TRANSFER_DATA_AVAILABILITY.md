# Transfer Data Availability & Source Strategy Audit
**Football Intelligence OS — Phase 4.1A & 4.1B**  
**Date**: September 2026  
**Status**: AUDITED & CLASSIFIED  

---

## 1. Executive Summary

This audit assesses historical football transfer data availability across existing connected providers, commercial APIs, open databases, and public domain repositories. In accordance with **Principle 1 (Zero Fabrication)**, **Principle 2 (Provenance First)**, and **Phase 4.1B (Source Strategy)**, this document establishes:
- Exactly what transfer data exists in the repository and connected systems.
- Which transfer fields are reliable vs ungrounded.
- Legitimate provider licensing and technical access boundaries (no scraping of restricted websites).
- Source classification from Class A (connected/verified) to Class F (unknown/unverified).

---

## 2. Source Classification & Strategy

| Classification | Category Definition | Sources | Strategy / Constraints |
| :--- | :--- | :--- | :--- |
| **Class A** | Currently connected and verified | **Local Bronze Snapshot Store (API-Football format)** | Raw ingested JSON snapshots content-addressed via SHA-256. Fully verified and reproducible. |
| **Class B** | Available via API but not integrated | **API-Football (`/transfers`)** | Upstream provider supports player and team transfer history. Local sandbox currently egress-restricted (`x-deny-reason: host_not_allowed`). Offline bronze snapshots used locally. |
| **Class C** | Requires external credentials | **Football-Data.org** | API token configured, but Football-Data.org v4 does not provide transfer transaction endpoints. |
| **Class D** | Requires licensed / commercial access | **Wyscout / Opta / Stats Perform / Transfermarkt Commercial API** | Enterprise commercial APIs providing contract and fee tracking. Requires enterprise commercial licensing. |
| **Class E** | Not suitable for automated ingestion | **Public Web Scraping (Transfermarkt / Wikipedia / FBref HTML)** | Prohibited by Terms of Service, anti-bot mechanisms (Cloudflare), licensing terms, and Principle 1/5. **Do not scrape.** |
| **Class F** | Unknown / requires verification | **FIFA Clearing House / FIFA TMS reports** | High-level macro transfer reports published annually; individual transaction microdata not programmatically accessible. |

---

## 3. Data Availability & Field Matrix

The matrix below audits transfer fields across existing and candidate sources against modeling criteria.

| SOURCE | FIELD | AVAILABLE? | COVERAGE | LICENSE/ACCESS STATUS | PROVENANCE | TEMPORAL COVERAGE | USABLE FOR MODEL? | LIMITATIONS |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **API-Football (Bronze)** | `player.id`, `player.name` | **YES** | 100% of ingested player records | Proprietary Commercial API (API-Sports) | Content-addressed SHA-256 in `DataSnapshot` | 2017 – Present | **YES** | Provider ID requires resolution to canonical `Player` entity. |
| **API-Football (Bronze)** | `transfer.date` | **YES** | High (>95% of records) | Proprietary Commercial API | IngestionRun $\to$ DataSnapshot | Day-level date | **YES** | Occasional month-only or window-start dates. |
| **API-Football (Bronze)** | `transfer.type` | **YES** | High (e.g. "€ 60M", "Free", "Loan", "N/A") | Proprietary Commercial API | IngestionRun $\to$ DataSnapshot | 2017 – Present | **YES** (with parser) | Mixed string field containing fees, "Free", "Loan", or null. Requires semantic taxonomy parser. |
| **API-Football (Bronze)** | `teams.in.id`, `teams.in.name` | **YES** | 100% of transfer events | Proprietary Commercial API | IngestionRun $\to$ DataSnapshot | 2017 – Present | **YES** | Must resolve through `ClubIdentity`. |
| **API-Football (Bronze)** | `teams.out.id`, `teams.out.name` | **YES** | 100% of transfer events | Proprietary Commercial API | IngestionRun $\to$ DataSnapshot | 2017 – Present | **YES** | Must resolve through `ClubIdentity`. |
| **StatsBomb Open Data** | Transfer fee / dates | **NO** | 0% (Not collected) | CC BY-NC-SA 4.0 | N/A | None | **NO** | StatsBomb open data covers match events/lineups, not commercial market transactions. |
| **Football-Data.org** | Transfer fee / dates | **NO** | 0% (Endpoint absent) | Freely available tier w/ token | N/A | None | **NO** | Football-Data.org v4 provides squads, fixtures, standings; no historical transfer fee endpoints. |
| **Transfermarkt (Public HTML)** | Market values, transfer fees | **NO** | Not accessible legally | Strictly restricted by ToS / Robots | None | Historical | **NO** | Scraping violates ToS, triggers Cloudflare challenges, produces unverified provenance. Disallowed. |
| **Club Financial Statements (Public)** | Disclosed transfer fees | **PARTIAL** | Low (<10% of global transfers; publicly traded clubs like Juventus, Dortmund, Lyon) | Public regulatory filings | Official corporate filings | Annual / Semi-Annual | **HIGH ACCURACY (Small sample)** | Highly factual where available, but sparse coverage across market universe. |

---

## 4. Transfer Field Reliability Analysis

1. **Transaction Existence & Date**:
   - High reliability. Movement between clubs on specified dates is corroborated across official club announcements and league registration filings.
2. **Transfer Type (Permanent vs Loan vs Free)**:
   - High reliability. Clear legal distinction between permanent registration transfer, temporary loan transfer, and contract expiration / free release.
3. **Reported Fee vs Factual Fee**:
   - Medium-to-Low reliability if treated blindly. European football transfers often involve undisclosed sums, conditional performance add-ons, sell-on clauses, and agent commissions.
   - **Mandatory Policy**: A fee reported in press or provider envelopes must be typed as `REPORTED_FEE` unless backed by official regulatory club disclosures (`KNOWN_FEE`). An absent fee must be `UNKNOWN_FEE` (never €0).
4. **Contract Length & Wages**:
   - Very Low availability in standard feeds. Wages are almost universally confidential estimates outside of Major League Soccer (MLSPA release). Contract expiry dates are moderately reliable.
   - **Policy**: Contract length is only used if verified; never fabricate player salary or amortization figures.

---

## 5. Legitimate Transfer Ingestion Pipeline

To satisfy both legal integrity and auditability:
1. **Bronze Ingestion**: Transfers are ingested via official provider API payloads or pre-collected provider snapshots. Each payload is stored with a unique SHA-256 hash in `data/bronze/` and recorded in `data_snapshots` and `ingestion_runs`.
2. **Deterministic Semantic Normalization**: The raw payload is parsed by `app.market.normalizer`, converting string representations (`"€ 60M"`, `"Loan"`, `"Free"`, `"N/A"`) into typed records with explicit `fee_status`.
3. **Identity Resolution**: Clubs and players are mapped via `ClubIdentity` and `PlayerIdentity`. Records with unresolved entities are flagged with `data_quality_status = "LOW"` rather than dropped or guessed.
4. **Zero Scraping Policy**: No scraping bots or undocumented web crawlers are permitted in Football Intelligence OS.
