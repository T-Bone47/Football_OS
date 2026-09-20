"""Tactical Fit Explainability Engine (Phase 2 Slice 3).
Generates factual, evidence-based natural language explanations for 'Why Fit' and 'Why Not Fit'
grounded strictly in numerical dimensional evidence.
"""
from __future__ import annotations

from typing import Any

from app.tactical.contexts import TacticalContext


def generate_tactical_explanations(
    player_name: str,
    player_position: str | None,
    position_fit: float,
    role_fit: float,
    dimension_breakdown: dict[str, Any],
    style_fit: float | None,
    context: TacticalContext,
    confidence: str,
    sample_minutes: int,
) -> dict[str, list[str]]:
    """Generates structured, traceable rationales for tactical suitability and deficits."""
    why_fit: list[str] = []
    why_not_fit: list[str] = []

    # 1. Positional Alignment
    if position_fit >= 0.85:
        why_fit.append(
            f"Strong positional alignment: {player_name} ({player_position or 'natural'}) fits target {context.target_position} position in {context.formation}."
        )
    elif position_fit < 0.50:
        why_not_fit.append(
            f"Positional mismatch: {player_name} ({player_position or 'Unknown'}) is outside preferred {context.target_position} profile."
        )

    # 2. Role Archetype Alignment
    if role_fit >= 0.80:
        why_fit.append(
            f"Strong functional role alignment with target archetype '{context.target_role}'."
        )
    elif role_fit < 0.55:
        why_not_fit.append(
            f"Role mismatch: {player_name}'s natural tendency deviates from '{context.target_role}' requirements (role fit: {role_fit:.2f})."
        )

    # 3. Dimensional Strengths (Why Fit)
    strong_dims = sorted(
        [
            (dim, data) for dim, data in dimension_breakdown.items()
            if data["fit_score"] >= 0.70 and data["player_score"] >= 0.45
        ],
        key=lambda x: (x[1]["fit_score"], x[1]["importance_weight"]),
        reverse=True,
    )
    for dim, data in strong_dims[:3]:
        why_fit.append(
            f"High {dim} alignment: player score ({data['player_score']:.2f}) meets required strength ({data['required_strength']:.2f}) with fit score {data['fit_score']:.2f}."
        )

    # 4. Dimensional Deficits & Bottlenecks (Why Not Fit)
    deficit_dims = sorted(
        [
            (dim, data) for dim, data in dimension_breakdown.items()
            if data["deficit"] > 0.0 or data["fit_score"] < 0.60
        ],
        key=lambda x: (x[1]["deficit"], -x[1]["fit_score"]),
        reverse=True,
    )
    for dim, data in deficit_dims[:3]:
        if data["deficit"] > 0:
            why_not_fit.append(
                f"{dim.capitalize()} shortfall: player score ({data['player_score']:.2f}) is below required minimum threshold ({data['minimum_threshold']:.2f}) with deficit -{data['deficit']:.2f}."
            )
        else:
            why_not_fit.append(
                f"{dim.capitalize()} divergence: player score ({data['player_score']:.2f}) deviates from required target ({data['required_strength']:.2f})."
            )

    # 5. Team Style Alignment
    if style_fit is not None:
        if style_fit >= 0.70:
            style_desc = context.possession_style or context.pressing_style or "team system"
            why_fit.append(f"Compatible with {style_desc} style demands (style fit: {style_fit:.2f}).")
        elif style_fit < 0.50:
            style_desc = context.possession_style or context.pressing_style or "team system"
            why_not_fit.append(f"Frictional fit with {style_desc} style profile (style fit: {style_fit:.2f}).")

    # 6. Sample Evidence Status
    if confidence == "INSUFFICIENT_DATA":
        why_not_fit.insert(
            0,
            f"Insufficient sample evidence: {player_name} has only {sample_minutes} recorded minutes (minimum required: 450 mins). Scores represent uncalibrated preliminary tendencies.",
        )

    if not why_fit:
        why_fit.append("Basic baseline compatibility across non-critical secondary metrics.")

    if not why_not_fit:
        why_not_fit.append("No critical tactical bottlenecks identified for this system setup.")

    return {
        "why_fit": why_fit,
        "why_not_fit": why_not_fit,
    }
