#!/usr/bin/env python3
"""Golden-set evaluation for the FIO grounded assistant.

Runs the golden cases in ``tests/ai/golden_set.json`` against the live provider and
reports the metrics that can be measured deterministically:

* tool-selection accuracy (did the expected tool run?);
* evidence-supported claim rate (were the answer's numbers found in the evidence?);
* unsupported numeric claim rate;
* epistemic-status coverage (was the evidence labelled as expected?);
* coverage/caveat disclosure for the cases that demand it;
* latency distribution and token usage.

The evaluation is opt-in: it needs a configured provider and network access. Run it
with ``--live``; without it the script only validates the golden set itself.

    python tools/evaluate_grounded_copilot.py --live --output docs/evidence/ai/evaluation.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.llm.tools.base import EpistemicStatus  # noqa: E402
from app.llm.tools.orchestrator import GroundedCopilot  # noqa: E402

GOLDEN = ROOT / "tests" / "ai" / "golden_set.json"


def load_cases() -> list[dict[str, Any]]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]


def _daily_budget_exhausted(error: str) -> bool:
    """True when the provider refused because a request budget is spent.

    The orchestrator reports the provider error by type (the detail stays in the
    server log), so a rate-limit error of any kind stops the batch: continuing
    would only produce more refusals.
    """
    lowered = error.lower()
    return (
        "tokens per day" in lowered
        or "tpd" in lowered
        or "ratelimit" in lowered
        or "rate limit" in lowered
    )


def score_case(case: dict[str, Any], result: Any) -> dict[str, Any]:
    """Score one case against its golden requirements."""
    tools_run = [entry.get("tool") for entry in result.tools]
    expected = set(case.get("expected_tools") or [])
    permitted = set(case.get("permitted_tools") or [])

    tool_hit = bool(expected & set(tools_run))
    unexpected_tools = [name for name in tools_run if name and permitted and name not in permitted]
    evidence_statuses = {item.epistemic_status.value for item in result.evidence}
    expected_statuses = set(case.get("expected_epistemic_status") or [])
    status_hit = bool(evidence_statuses & expected_statuses) or (
        not result.evidence and "INSUFFICIENT_DATA" in expected_statuses
    )
    required_evidence_types = set(case.get("required_evidence") or [])
    evidence_types = {item.entity_type for item in result.evidence}
    evidence_hit = not required_evidence_types or bool(required_evidence_types & evidence_types)

    unsupported = result.validation.unsupported_numbers
    numbers_total = len(result.validation.supported_numbers) + len(unsupported)
    caveat_text = (result.coverage_note or "") + " " + result.answer.lower()
    caveat_hit = True
    for needle in case.get("required_caveats") or []:
        key = needle.lower().split()[0]
        if key not in caveat_text:
            caveat_hit = False
            break

    return {
        "id": case["id"],
        "status": result.status,
        "tools_run": tools_run,
        "tool_selection_hit": tool_hit,
        "unexpected_tools": unexpected_tools,
        "evidence_count": len(result.evidence),
        "evidence_types": sorted(evidence_types),
        "evidence_required_hit": evidence_hit,
        "epistemic_statuses": sorted(evidence_statuses),
        "epistemic_status_hit": status_hit,
        "supported_numbers": len(result.validation.supported_numbers),
        "unsupported_numbers": unsupported,
        "numbers_total": numbers_total,
        "caveat_hit": caveat_hit,
        "grounded": result.validation.grounded,
        "latency_ms": result.latency_ms,
        "provider": result.provider,
        "model": result.model,
        "usage": result.usage,
        "answer_preview": (result.answer or "")[:400],
    }


async def run_live(
    cases: list[dict[str, Any]],
    output: Path,
    delay: float = 18.0,
    token_budget: int = 60_000,
) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    results: list[dict[str, Any]] = []
    tokens_used = 0
    skipped_budget = 0
    try:
        async with Session() as session:
            for index, case in enumerate(cases):
                if tokens_used >= token_budget:
                    skipped_budget += 1
                    results.append(
                        {
                            "id": case["id"],
                            "status": "SKIPPED_TOKEN_BUDGET",
                            "tool_selection_hit": False,
                            "epistemic_status_hit": False,
                            "evidence_required_hit": False,
                            "caveat_hit": False,
                            "grounded": False,
                            "supported_numbers": 0,
                            "unsupported_numbers": [],
                            "numbers_total": 0,
                            "latency_ms": 0,
                        }
                    )
                    continue
                copilot = GroundedCopilot(session=session)
                started = time.perf_counter()
                try:
                    answer = await copilot.answer(case["question"])
                    scored = score_case(case, answer)
                except Exception as exc:  # noqa: BLE001 - a failing case is a result
                    scored = {
                        "id": case["id"],
                        "status": "EXCEPTION",
                        "error": f"{type(exc).__name__}: {exc}",
                        "tool_selection_hit": False,
                        "epistemic_status_hit": False,
                        "evidence_required_hit": False,
                        "caveat_hit": False,
                        "grounded": False,
                        "supported_numbers": 0,
                        "unsupported_numbers": [],
                        "numbers_total": 0,
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                    }
                usage = scored.get("usage") or {}
                tokens_used += int(usage.get("total_tokens") or 0)
                results.append(scored)
                if scored.get("status") == "PROVIDER_ERROR" and _daily_budget_exhausted(
                    str(scored.get("error") or "")
                ):
                    # The provider's daily token budget is spent. The remaining
                    # cases are recorded as skipped instead of burning requests.
                    skipped_budget += len(cases) - index - 1
                    for remaining in cases[index + 1 :]:
                        results.append(
                            {
                                "id": remaining["id"],
                                "status": "SKIPPED_TOKEN_BUDGET",
                                "tool_selection_hit": False,
                                "epistemic_status_hit": False,
                                "evidence_required_hit": False,
                                "caveat_hit": False,
                                "grounded": False,
                                "supported_numbers": 0,
                                "unsupported_numbers": [],
                                "numbers_total": 0,
                                "latency_ms": 0,
                            }
                        )
                    print(
                        "provider daily token budget exhausted - the remaining cases were skipped",
                        flush=True,
                    )
                    break
                print(
                    f"[{index + 1}/{len(cases)}] {case['id']}: {scored.get('status')} "
                    f"tools={scored.get('tools_run')} "
                    f"unsupported={scored.get('unsupported_numbers')} "
                    f"tokens={tokens_used}",
                    flush=True,
                )
                if index + 1 < len(cases) and delay:
                    # The provider's token budget is per minute and shared by every
                    # request of a turn, so the cases are paced.
                    await asyncio.sleep(delay)
    finally:
        await engine.dispose()

    total = len(results) or 1
    latencies = [item.get("latency_ms", 0) for item in results]
    numbers_total = sum(item.get("numbers_total", 0) for item in results)
    unsupported_total = sum(len(item.get("unsupported_numbers") or []) for item in results)
    metrics = {
        "cases": len(results),
        "cases_skipped_token_budget": skipped_budget,
        "provider_tokens_used": tokens_used,
        "tool_selection_accuracy": round(
            sum(1 for item in results if item.get("tool_selection_hit")) / total, 3
        ),
        "epistemic_status_accuracy": round(
            sum(1 for item in results if item.get("epistemic_status_hit")) / total, 3
        ),
        "required_evidence_accuracy": round(
            sum(1 for item in results if item.get("evidence_required_hit")) / total, 3
        ),
        "caveat_disclosure_accuracy": round(
            sum(1 for item in results if item.get("caveat_hit")) / total, 3
        ),
        "grounded_answer_rate": round(
            sum(1 for item in results if item.get("grounded")) / total, 3
        ),
        "unsupported_numeric_claim_rate": round(
            unsupported_total / numbers_total, 3
        ) if numbers_total else None,
        "numeric_claims_checked": numbers_total,
        "latency_ms_p50": int(statistics.median(latencies)) if latencies else None,
        "latency_ms_max": max(latencies) if latencies else None,
        "unplanned_tool_rate": round(
            sum(1 for item in results if item.get("unexpected_tools")) / total, 3
        ),
    }
    payload = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "metrics": metrics, "results": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="run against the configured provider")
    parser.add_argument("--output", default="docs/evidence/ai/evaluation.json")
    parser.add_argument("--delay", type=float, default=18.0, help="seconds between cases")
    parser.add_argument(
        "--token-budget",
        type=int,
        default=60_000,
        help="stop after this many provider tokens (the Free tier allows 200 000 tokens/day)",
    )
    parser.add_argument(
        "--cases",
        nargs="*",
        default=None,
        help="only run these case ids (the provider's daily token budget is finite)",
    )
    args = parser.parse_args()
    cases = load_cases()
    if args.cases:
        wanted = set(args.cases)
        cases = [case for case in cases if case["id"] in wanted]
    if not args.live:
        print(
            json.dumps(
                {
                    "mode": "offline",
                    "cases": len(cases),
                    "note": (
                        "The golden set was validated (schema only). Run with --live to measure "
                        "tool selection, grounding and latency against the configured provider."
                    ),
                    "ids": [case["id"] for case in cases],
                },
                indent=2,
            )
        )
        return 0
    return asyncio.run(run_live(cases, Path(args.output), args.delay, args.token_budget))


if __name__ == "__main__":
    raise SystemExit(main())
