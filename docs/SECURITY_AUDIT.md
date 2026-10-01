# Security Audit & Copilot Sandboxing Architecture

## Overview
Phase 8 formalizes the application security posture, threat boundaries, and sandboxing guarantees. The system adheres to defense-in-depth principles across the web API, database interactions, and natural-language Scout Copilot workflows.

---

## 1. Threat Model & Security Boundaries

```
[ External User / Client ]
            │  HTTPS / Strict CORS
            ▼
┌────────────────────────────────────────────────────────┐
│ FastAPI Application Boundary                           │
│  - Strict Pydantic v2 Request Validation               │
│  - Correlation ID Injection & Secret Redaction         │
│  - Scout Analyst Session Auth (/api/auth/me)           │
└────────────────────────────────────────────────────────┘
            │
      ┌─────┴─────────────────────────────────┐
      ▼                                       ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│ Deterministic Services   │    │ Scout Copilot Sandbox    │
│  - UnifiedDecisionService│    │  - ScoutDecisionTools    │
│  - PredictionEngines     │    │  - Strictly Whitelisted  │
│  - Fully Parameterized   │    │  - Zero Execution Perms  │
└──────────────────────────┘    └──────────────────────────┘
            │                                 │
            └───────────────┬─────────────────┘
                            ▼
               ┌──────────────────────────┐
               │ PostgreSQL 15+ Database  │
               │  - Parameterized Queries │
               │  - Least Privilege Access│
               └──────────────────────────┘
```

---

## 2. SQL Injection Prevention & Type Boundary Validation

1. **Strict Type Coercion**:
   - Pydantic models reject invalid data types at the API boundary before execution reaches business logic.
   - UUID fields (`player_id`, `club_id`, `decision_id`) enforce strict RFC 4122 validation. Payloads such as `1; DROP TABLE players; --` raise validation errors immediately.
2. **Parameterized ORM Queries**:
   - All relational operations utilize SQLAlchemy ORM with bound parameters.
   - String fields (such as `tactical_context_id` or query parameters) are passed as bound query parameters, preventing SQL injection even under adversarial inputs.
3. **Verified in Test Suite**:
   - `test_pydantic_enforces_strict_types_preventing_sql_injection` in `test_phase8_security_and_performance.py`.
   - `test_sanitized_string_fields_prevent_sql_injection` in `test_phase8_security_and_performance.py`.

---

## 3. Scout Copilot Sandboxing & Tool Integrity

The Scout Copilot enables conversational decision intelligence while guaranteeing safety against code execution:

1. **Deterministic Tool Sandboxing (`ScoutDecisionTools`)**:
   - Copilot tools are restricted strictly to whitelisted domain methods:
     `get_player_intelligence`, `get_player_similarity`, `get_tactical_fit`, `get_market_context`, `get_valuation`, `get_transfer_risk`, `analyze_squad`, `simulate_transfer`, `get_match_prediction`, `compare_candidates`, `retrieve_evidence`.
   - **Prohibited Interfaces**: The tool registry exposes zero shell, subprocess, system, filesystem, raw SQL, or `eval`/`exec` primitives.
2. **Prompt Injection Resilience**:
   - Queries containing prompt injection attempts (`DROP TABLE`, `<script>`, `__import__('os')`) are parsed safely by standard string matching and routed strictly through deterministic calculation engines.
   - The orchestrator never dynamically executes user queries as code.

---

## 4. Zero Fabrication & Evidence Grounding Guarantee

The Scout Copilot provides an absolute guarantee regarding analytical accuracy:
- **No Hallucinated Numbers**: Valuations, contribution percentiles, similarity scores, and tactical fit metrics are sourced directly from deterministic engine outputs.
- **Truthful Empty States**: When candidate cohorts are empty or criteria cannot be met, the Copilot surfaces explicit, truthful caveats rather than fabricating plausible candidates.
- **Traceable Attribution**: Every Copilot response cites the underlying `decision_id` and references the associated evidence graph.
