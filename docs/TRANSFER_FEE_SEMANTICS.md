# Controlled Transfer Fee Semantics & Taxonomy
**Football Intelligence OS — Phase 4.1D**  
**Date**: September 2026  
**Status**: APPROVED & ACTIVE  

---

## 1. Architectural Mandate

In commercial football analytics, one of the most pervasive sources of model corruption is the sloppy conflation of missing financial data with zero values. A player moving on an "Undisclosed Fee" or a loan with an option to buy is fundamentally distinct from a player moving on a contractual "Free Transfer" (Bosman ruling). 

Furthermore, media-reported transfer fees often differ from officially audited regulatory disclosures by publicly traded clubs (e.g., Borussia Dortmund, Juventus, Olympique Lyonnais) or FIFA Clearing House figures.

To guarantee that Football Intelligence OS models are grounded, explainable, and free of silent fabrication, this document defines the **Controlled Transfer Fee Taxonomy** and associated operational invariants.

---

## 2. Controlled Fee Status Taxonomy

| Fee Status | Definition | `fee_value` Representation | Usable in Model Training? |
| :--- | :--- | :--- | :--- |
| **`KNOWN_FEE`** | Factual, regulatory-verified transfer compensation confirmed via club financial statement or official regulatory disclosure. | Exact numerical amount in original currency. | **YES (Highest weight)** |
| **`REPORTED_FEE`** | Press/media reported deal fee from reliable football industry sources (e.g., BBC, The Athletic, Fabrizio Romano). | Exact reported numerical amount in original currency. | **YES (Standard weight)** |
| **`ESTIMATED_FEE`** | Algorithmic, scout, or crowd-estimated market valuation (e.g., Transfermarkt MV, CIES estimate). | Numerical estimate. Flagged as non-factual. | **NO for target fees** (May only serve as comparison benchmark). |
| **`UNKNOWN_FEE`** | Transaction occurred, but compensation details are absent or not disclosed. | Strictly `null` (`None`). **NEVER 0.** | **NO as fee target**; usable for transaction volume / network graphs. |
| **`FREE_TRANSFER`** | Player out of contract, released, or signed under Bosman ruling. Zero transfer compensation paid to former club. | Explicitly `0.0` EUR. | **YES (Distinct categorical target / regime)**. |
| **`LOAN`** | Temporary sporting registration where economic and permanent registration rights remain with parent club. | Loan fee amount if reported; otherwise `null`. | **NO for permanent transfer valuation**; used in loan modeling. |
| **`LOAN_WITH_OPTION`** | Temporary sporting loan containing a non-obligatory buyout clause. | Loan fee amount if reported; option value tracked in metadata. | **NO for permanent transfer valuation**. |
| **`LOAN_WITH_OBLIGATION`**| Temporary sporting loan containing mandatory conditional or unconditional buyout obligation. | Equivalent to deferred permanent transfer if obligation terms triggered. | **CONDITIONAL** (Requires qualification check). |
| **`UNDISCLOSED`** | Clubs explicitly published that the fee is undisclosed to the public. | Strictly `null`. **NEVER 0.** | **NO as fee target**. |
| **`NOT_APPLICABLE`** | Return from loan, youth academy promotion, amateur registration. | Strictly `null`. | **NO**. |

---

## 3. The Core Invariants

### Invariant 1: Unknown is NOT Zero
$$\text{UNKNOWN\_FEE} \ne 0.00$$
$$\text{UNDISCLOSED} \ne 0.00$$

A missing fee indicates lack of visibility, not absence of economic consideration. Ingesting an undisclosed Premier League transfer as €0 would severely bias any valuation model downward.

### Invariant 2: Free Transfer is Distinct from Unknown
$$\text{FREE\_TRANSFER} \iff \text{Player Contract Expired / Mutual Termination}$$

A free transfer carries real economic meaning: the buying club paid no transfer compensation to the selling club, though signing bonuses and player wages may be elevated. It is encoded with `fee_status = FREE_TRANSFER` and `fee_value = 0.0`.

### Invariant 3: Currency Provenance Preservation
The system never overwrites the source currency amount. If an English club reports a fee of £25,000,000:
- `fee_value` = `25000000.0`
- `fee_currency` = `"GBP"`
- `fee_eur_normalized` = `29250000.0` (using versioned `FX_RATES_V1["GBP"] = 1.17`)

Downstream models and UI consumers can query either the native reported currency or the normalized EUR baseline, with conversion versioning preserved.

### Invariant 4: Temporary vs Permanent Separation
$$\text{is\_loan} = \text{True} \implies \text{is\_permanent} = \text{False}$$

Loans must never be pooled with permanent transfers when calculating historical price distributions or valuation baselines without explicit structural adjustment.

---

## 4. Parser Reference Table

| Raw Provider String | Parsed `fee_value` | Parsed `fee_currency` | Parsed `fee_status` | Parsed `transfer_type` | `is_loan` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `"€ 60M"` | `60,000,000.0` | `"EUR"` | `REPORTED_FEE` | `PERMANENT` | `False` |
| `"£ 17.5M"` | `17,500,000.0` | `"GBP"` | `REPORTED_FEE` | `PERMANENT` | `False` |
| `"$ 12M"` | `12,000,000.0` | `"USD"` | `REPORTED_FEE` | `PERMANENT` | `False` |
| `"Free"` | `0.0` | `"EUR"` | `FREE_TRANSFER` | `FREE` | `False` |
| `"Loan"` | `null` | `null` | `LOAN` | `LOAN` | `True` |
| `"Loan with option"` | `null` | `null` | `LOAN_WITH_OPTION` | `LOAN` | `True` |
| `"€ 5M loan"` | `5,000,000.0` | `"EUR"` | `LOAN` | `LOAN` | `True` |
| `"Back from loan"` | `null` | `null` | `NOT_APPLICABLE` | `RETURN_FROM_LOAN`| `False` |
| `"Undisclosed"` | `null` | `null` | `UNDISCLOSED` | `PERMANENT` | `False` |
| `"- "` or `"N/A"` | `null` | `null` | `UNKNOWN_FEE` | `PERMANENT` | `False` |
