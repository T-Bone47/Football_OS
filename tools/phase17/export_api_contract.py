"""Writes tests/contracts/ops_api_contract.json from the live OpenAPI schema.
Run after an intentional API change; tests/unit/test_phase17_api_contract.py
fails on any unreviewed difference.
"""
from __future__ import annotations

import json

from common import ROOT

from app.main import app


def contract() -> dict:
    spec = app.openapi()
    out = {}
    for path, methods in sorted(spec["paths"].items()):
        if not path.startswith("/api/v1/ops"):
            continue
        for method, op in sorted(methods.items()):
            params = sorted(f"{p['in']}:{p['name']}{'*' if p.get('required') else ''}" for p in op.get("parameters", []))
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}).get("$ref")
            out[f"{method.upper()} {path}"] = {"params": params, "body": body.rsplit("/", 1)[-1] if body else None}
    return out


if __name__ == "__main__":
    path = ROOT / "tests" / "contracts" / "ops_api_contract.json"
    path.write_text(json.dumps(contract(), indent=2, sort_keys=True) + "\n")
    print("wrote", path)
