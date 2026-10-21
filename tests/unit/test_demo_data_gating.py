"""Seeded Phase 13/14 demonstration data must never exist in production (audit R24; stage-2 item 2).

Static checks parse source (no web stack); the runtime check instantiates the real classes.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from app.demo import demo_data_allowed

APP = Path(__file__).resolve().parents[2] / "apps" / "api" / "app"
MODULES = sorted(list((APP / "phase13").glob("*.py")) + list((APP / "phase14").glob("*.py")))


@pytest.mark.parametrize(
    "env,expected",
    [({}, False), ({"FOOTBALL_OS_DEMO_DATA": "1"}, True), ({"FOOTBALL_OS_DEMO_DATA": "0"}, False),
     ({"FOOTBALL_OS_DEMO_DATA": "1", "ENVIRONMENT": "production"}, False), ({"FOOTBALL_OS_DEMO_DATA": "1", "ENVIRONMENT": "Production "}, False),
     ({"FOOTBALL_OS_DEMO_DATA": "1", "ENVIRONMENT": "development"}, True)],
)
def test_demo_mode_is_opt_in_and_never_available_in_production(monkeypatch, env, expected):
    for key in ("FOOTBALL_OS_DEMO_DATA", "ENVIRONMENT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert demo_data_allowed() is expected


def _seeding_classes():
    out = {}
    for path in MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            init = next((m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == "__init__"), None)
            if init and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr.startswith("_seed") for n in ast.walk(init)):
                out[cls.name] = (path, init)
    return out


def test_there_are_seeding_classes_to_guard():
    assert len(_seeding_classes()) >= 16  # Phase 13: 5, Phase 14: 11


def test_every_seed_call_sits_under_the_seed_demo_flag():
    unguarded = []
    for name, (path, init) in _seeding_classes().items():
        assert "seed_demo" in [a.arg for a in init.args.args], f"{name}.__init__ has no seed_demo parameter"
        guarded_calls = {
            id(c)
            for node in ast.walk(init)
            if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "seed_demo"
            for c in ast.walk(node)
            if isinstance(c, ast.Call)
        }
        for call in (n for n in ast.walk(init) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr.startswith("_seed")):
            if id(call) not in guarded_calls:
                unguarded.append(f"{name} ({path.name}:{call.lineno})")
    assert not unguarded, f"seed calls outside `if seed_demo:`: {unguarded}"


def test_module_level_instances_seed_only_in_demo_mode():
    classes = set(_seeding_classes())
    bad = []
    for path in MODULES:
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and getattr(node.value.func, "id", "") in classes:
                kw = next((k for k in node.value.keywords if k.arg == "seed_demo"), None)
                if kw is None or ast.unparse(kw.value) != "demo_data_allowed()":
                    bad.append(f"{path.name}:{node.lineno}")
    assert not bad, f"singletons that do not gate seeding on demo mode: {bad}"


def test_phase13_and_14_routers_are_demo_only_over_http():
    tree = ast.parse((APP / "main.py").read_text(encoding="utf-8"))
    gated = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "include_router" and node.args:
            dep = next((k.value for k in node.keywords if k.arg == "dependencies"), None)
            gated[ast.unparse(node.args[0])] = dep is not None and "DEMO_ONLY" in ast.unparse(dep)
    assert gated["phase13_router"] and gated["phase14_router"]
    # Phase 11 (hand-typed competition coverage/readiness) and Phase 12 (learning loop, challengers, discovery) are
    # built on the same typed figures and hardcoded model claims.
    assert gated["phase11_router"] and gated["phase12_router"]
    assert "require_demo_data" in (APP / "main.py").read_text(encoding="utf-8")


def _held_items(obj) -> int:
    return sum(len(v) for v in vars(obj).values() if isinstance(v, (dict, list, set, tuple)))


def test_default_instances_are_empty_and_demo_instances_are_populated():
    checked = 0
    for name, (path, _) in _seeding_classes().items():
        module = importlib.import_module(f"app.{path.parent.name}.{path.stem}")
        cls = getattr(module, name)
        try:
            empty, seeded = cls(), cls(seed_demo=True)
        except TypeError:
            continue  # needs collaborators (e.g. a ledger); covered by the static checks above
        assert _held_items(empty) == 0, f"{name}() starts with data in production mode"
        assert _held_items(seeded) > 0, f"{name}(seed_demo=True) holds no demo data"
        checked += 1
    assert checked >= 10


def test_phase10_model_lifecycle_routes_are_demo_only():
    """phase10/model_lifecycle.py seeds a PRODUCTION-stage match model that has no artifact."""
    tree = ast.parse((APP / "api" / "routes_phase10.py").read_text(encoding="utf-8"))
    routes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(isinstance(c, ast.Name) and c.id == "model_lifecycle" for c in ast.walk(n))]
    assert len(routes) >= 2
    for route in routes:
        assert "require_demo_data" in ast.unparse(route), f"{route.name} serves seeded lifecycle records outside demo mode"
