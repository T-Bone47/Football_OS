"""Every route requires a verified principal except the explicit public probes (R9/R10/R17).

The static tests parse source (no web stack needed); the runtime test exercises the real app.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "apps" / "api" / "app"
PUBLIC_PROBES = {"/health", "/readiness", "/health/ready", "/api/status"}  # liveness/readiness/status only
_MAIN = ast.parse((APP / "main.py").read_text(encoding="utf-8"))


def _kw(call: ast.Call, name: str):
    return next((k.value for k in call.keywords if k.arg == name), None)


def test_every_router_is_included_with_the_authentication_dependency():
    includes = [n for n in ast.walk(_MAIN) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "include_router"]
    assert len(includes) >= 10
    unprotected = [ast.unparse(c.args[0]) for c in includes if _kw(c, "dependencies") is None]
    assert not unprotected, f"routers included without dependencies=: {unprotected}"


def test_main_routes_are_public_probes_or_protected():
    offenders = []
    for node in ast.walk(_MAIN):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if isinstance(deco, ast.Call) and getattr(deco.func, "value", None) is not None and getattr(deco.func.value, "id", "") == "app":
                path = deco.args[0].value
                protected = _kw(deco, "dependencies") is not None or "get_principal" in ast.unparse(node.args)
                if path not in PUBLIC_PROBES and not protected:
                    offenders.append(path)
    assert not offenders, f"unprotected non-probe routes: {offenders}"


def test_fake_identity_endpoints_are_gone():
    paths = {ast.literal_eval(d.args[0]) for n in ast.walk(_MAIN) if isinstance(n, ast.FunctionDef) or isinstance(n, ast.AsyncFunctionDef)
             for d in n.decorator_list if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant)}
    assert not [p for p in paths if p.startswith("/api/auth")], "identity endpoints belong to the identity service, not a stub"
    leaked = [str(p) for p in APP.rglob("*.py") if re.search(r"\b(scout_01|admin_01|analyst_01|org_arsenal)\b", p.read_text(encoding="utf-8"))]
    assert not leaked, f"seeded demo identities found in: {leaked}"


def test_cors_origins_come_from_validated_settings_not_a_wildcard():
    cors = next(n for n in ast.walk(_MAIN) if isinstance(n, ast.Call) and any(isinstance(a, ast.Name) and a.id == "CORSMiddleware" for a in n.args))
    origins = _kw(cors, "allow_origins")
    assert isinstance(origins, ast.Call) and getattr(origins.func, "id", "") == "parse_cors_origins"
    assert "'*'" not in ast.unparse(cors), "no wildcard origins/methods/headers on a credentialed CORS policy"
