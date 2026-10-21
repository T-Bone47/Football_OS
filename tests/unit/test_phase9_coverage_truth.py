"""Phase 9 coverage audit: provenance, missingness and validation are measured or unknown, never assumed (audit R7/N11)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from app.phase9.coverage_audit import CoverageQuality, _assess_quality, build_coverage_matrix

APP = Path(__file__).resolve().parents[2] / "apps" / "api" / "app"


def _value(x):
    return getattr(x, "value", x)


def test_a_file_full_of_records_is_not_thereby_validated_complete_or_excellent(tmp_path):
    fixtures = tmp_path / "bronze" / "api-football" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "f1.json").write_text(json.dumps({"response": [{}] * 5000}))
    matrix = build_coverage_matrix(tmp_path)
    assert matrix.dimensions["matches"].record_count == 5000
    for name, dim in matrix.dimensions.items():
        assert dim.provenance_completeness is None, f"{name}: provenance was assumed (1.0 whenever records exist)"
        assert dim.missingness_rate is None, f"{name}: missingness was assumed to be 0.0"
        assert _value(dim.validation_status) != "VALIDATED", f"{name}: marked VALIDATED without any validation"
        assert _value(dim.coverage_quality) not in ("EXCELLENT", "GOOD"), f"{name}: quality rated from assumed constants"


def test_unmeasured_quality_is_capped_below_good_whatever_the_record_count():
    assert _value(_assess_quality(0, None, None)) == "ABSENT"
    assert _value(_assess_quality(10_000_000, None, None)) in ("PARTIAL", "SPARSE", "MINIMAL")
    assert _value(_assess_quality(10_000_000, 1.0, 0.0)) in ("EXCELLENT", "GOOD")  # the measured path is unchanged


def test_coverage_routes_never_compare_an_unmeasured_value():
    """Any comparison on provenance_completeness / missingness_rate must sit under an `is None` guard."""
    tree = ast.parse((APP / "api" / "routes_data_coverage.py").read_text(encoding="utf-8"))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    unguarded = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Attribute) and node.left.attr in ("provenance_completeness", "missingness_rate"):
            cursor, guarded = node, False
            while cursor in parents:
                cursor = parents[cursor]
                if isinstance(cursor, ast.IfExp) and "is None" in ast.unparse(cursor.test):
                    guarded = True
                    break
            if not guarded:
                unguarded.append(node.lineno)
    assert not unguarded, f"unguarded comparisons of unmeasured values at lines {unguarded}"


def test_the_release_report_route_is_demo_only():
    """generate_phase9_report prints a PRODUCTION_VALIDATED certificate from constants (test_passed=413, 2026-09-26 baseline)."""
    tree = ast.parse((APP / "api" / "routes_data_coverage.py").read_text(encoding="utf-8"))
    route = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "generate_phase9_report" for c in ast.walk(n))
    )
    assert "require_demo_data" in ast.unparse(route), "the certificate route must depend on require_demo_data"
    assert "test_passed=413" not in (APP / "api" / "routes_data_coverage.py").read_text(encoding="utf-8")
