"""Static guard: SYNTHETIC_FEATURES must match what dataset.py actually does (no import of the ML stack)."""
from __future__ import annotations

import ast
from pathlib import Path

ML_DIR = Path(__file__).resolve().parents[2] / "apps" / "api" / "app" / "market" / "ml"
_REAL_SOURCES = {"r", "cohort_median", "cohort_iqr", "prior_fees", "age_factor"}  # real record / prior-fee statistics


def _tuple_constant(path: Path, name: str) -> set[str]:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == name:
            return {elt.value for elt in node.value.elts}
    raise AssertionError(f"{name} not found in {path.name}")


def _builder_feature_exprs() -> dict[str, ast.AST]:
    for node in ast.walk(ast.parse((ML_DIR / "dataset.py").read_text())):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "feat_dict" and isinstance(node.value, ast.Dict):
            return {k.value: v for k, v in zip(node.value.keys, node.value.values)}
    raise AssertionError("feat_dict not found in dataset.py")


def _is_real(key: str, expr: ast.AST) -> bool:
    names = {n.id for n in ast.walk(expr) if isinstance(n, ast.Name)}
    return bool(names & _REAL_SOURCES) or (isinstance(expr, ast.Name) and expr.id == "age") or key == "position_group_encoded"


def test_declared_synthetic_features_match_the_training_builder():
    exprs = _builder_feature_exprs()
    detected = {k for k, v in exprs.items() if not _is_real(k, v)}
    declared = _tuple_constant(ML_DIR / "feature_provenance.py", "SYNTHETIC_FEATURES")
    assert detected == declared, f"undeclared={sorted(detected - declared)} stale={sorted(declared - detected)}"


def test_observed_and_synthetic_partition_every_builder_feature():
    exprs = set(_builder_feature_exprs())
    synthetic = _tuple_constant(ML_DIR / "feature_provenance.py", "SYNTHETIC_FEATURES")
    observed = _tuple_constant(ML_DIR / "feature_provenance.py", "OBSERVED_FEATURES")
    assert not synthetic & observed and synthetic | observed == exprs


def test_serving_never_zero_fills_model_features():
    """Regression: service.py used feat_dict.get(name, 0.0) for 30 model features, 23 of them mis-named."""
    tree = ast.parse((ML_DIR / "service.py").read_text())
    zero_fills = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "get"
        and len(n.args) == 2
        and isinstance(n.args[1], ast.Constant)
        and type(n.args[1].value) is float  # not False, which == 0.0 in Python
        and n.args[1].value == 0.0
    ]
    assert not zero_fills, f"service.py zero-fills missing values at lines {zero_fills}"
    source = (ML_DIR / "service.py").read_text()
    assert "np.nan" in source and "null_count=null_count" in source
