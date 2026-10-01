"""Deterministic Explanation Generator (Phase 3.2L).
Produces auditable, rule-based natural language explanations grounded directly
in observable statistical and dimensional deltas. Zero LLM hallucinations.
"""
from __future__ import annotations

from typing import Any


class DeterministicExplanationGenerator:
    """Generates explainable drivers for player strengths, divergences, and confidence."""

    def generate_explanations(
        self,
        dimensions: dict[str, Any],
        raw_metrics: dict[str, Any],
        peer_benchmarks: dict[str, Any],
        sample_minutes: int,
        sample_matches: int,
        confidence: str,
        status: str,
    ) -> dict[str, list[str]]:
        why_strong: list[str] = []
        why_different: list[str] = []
        why_low_confidence: list[str] = []

        # 1. Why Low Confidence / Data Sufficiency Explanations
        if status in {"INSUFFICIENT_SAMPLE", "INSUFFICIENT_DATA"} or confidence in {"LOW", "INSUFFICIENT_SAMPLE", "INSUFFICIENT_DATA"}:
            if sample_minutes == 0:
                why_low_confidence.append("Zero competitive match minutes recorded in canonical evaluation window.")
            elif sample_minutes < 270:
                why_low_confidence.append(
                    f"Sample exposure ({sample_minutes} mins across {sample_matches} matches) is below minimum threshold (270 mins) for unbiased percentile calculation."
                )
            elif sample_minutes < 600:
                why_low_confidence.append(
                    f"Sub-600 minute sample ({sample_minutes} mins) provides preliminary evidence with higher variance."
                )

        # 2. Why Strong (evaluated dimensions >= 0.70 score or >= 75th percentile)
        benchmarks = peer_benchmarks.get("metrics") or {}
        for dim_name, dim_item in (dimensions or {}).items():
            score = getattr(dim_item, "score", None) if hasattr(dim_item, "score") else dim_item.get("score")
            pct = getattr(dim_item, "percentile", None) if hasattr(dim_item, "percentile") else dim_item.get("percentile")

            if score is not None and score >= 0.70:
                p_display = pct if pct is not None else round(score * 100)
                why_strong.append(
                    f"High {dim_name} contribution rating ({score:.2f}, P{p_display:.0f}) relative to positional peers."
                )

        for m_name, m_data in benchmarks.items():
            pct = m_data.get("percentile")
            val = m_data.get("value_p90")
            if pct is not None and pct >= 80.0:
                clean_metric = m_name.replace("_p90", "").replace("_", " ")
                why_strong.append(f"Top-tier {clean_metric} output ({val}/90, P{pct:.0f}).")

        # 3. Why Different / Divergent (lowest percentiles or notable tactical imbalances)
        for m_name, m_data in benchmarks.items():
            pct = m_data.get("percentile")
            val = m_data.get("value_p90")
            if pct is not None and pct <= 25.0:
                clean_metric = m_name.replace("_p90", "").replace("_", " ")
                why_different.append(
                    f"Subdued {clean_metric} output ({val}/90, P{pct:.0f}) compared to position baseline."
                )

        return {
            "why_strong": why_strong[:4] if why_strong else ["Metrics align with standard position baselines."],
            "why_different": why_different[:4] if why_different else ["Balanced profile without severe positional outliers."],
            "why_low_confidence": why_low_confidence,
        }
