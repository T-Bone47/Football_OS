"""Backend ownership and the frontend contract (audit R14, N16).

Two backends sit behind one origin. Each URL has exactly one owner, the gateway config routes by prefix, and every
path the frontend calls exists on its owner. Static: parses source and deploy/nginx.conf, no web stack needed.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_APP = ROOT / "apps" / "api" / "app"
IDENTITY = ROOT / "Football_OS-frontend" / "backend" / "server.py"
FRONTEND_SRC = ROOT / "Football_OS-frontend" / "frontend" / "src"
NGINX = ROOT / "deploy" / "nginx.conf"
_VERBS = ("get", "post", "put", "patch", "delete")


def _api_routes() -> set[str]:
    routes = set()
    for path in sorted((API_APP / "api").glob("routes_*.py")) + [API_APP / "main.py"]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prefix = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "APIRouter":
                for kw in node.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        prefix = kw.value.value
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for deco in node.decorator_list:
                    if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute) and deco.func.attr in _VERBS and deco.args and isinstance(deco.args[0], ast.Constant):
                        routes.add((prefix if path.name != "main.py" else "") + deco.args[0].value)
    return routes


def _identity_routes() -> set[str]:
    return {"/api" + m.group(2) for m in re.finditer(r'@api_router\.(get|post|put|patch|delete)\("([^"]*)"', IDENTITY.read_text(encoding="utf-8"))}


def _norm(path: str) -> str:
    return re.sub(r"\{[^}/]*\}", "{}", path).rstrip("/") or "/"


def _nginx_prefixes() -> dict[str, str]:
    text = NGINX.read_text(encoding="utf-8")
    return {m.group(1): m.group(2) for m in re.finditer(r"location\s+(/api/?[^\s{]*)\s*\{[^}]*?proxy_pass\s+http://(\w+)", text)}


def test_no_url_is_served_by_both_backends():
    overlap = {_norm(p) for p in _api_routes()} & {_norm(p) for p in _identity_routes()}
    assert not overlap, f"routes defined by both services: {sorted(overlap)}"


def test_the_identity_service_serves_only_auth_and_shortlists():
    """It used to also expose an unauthenticated Mongo write (/status), an ungrounded LLM copilot and a template root."""
    prefixes = ("/api/auth/", "/api/shortlists")
    stray = [p for p in _identity_routes() if not p.startswith(prefixes)]
    assert not stray, f"identity service routes outside its ownership: {stray}"
    source = IDENTITY.read_text(encoding="utf-8")
    for forbidden in ("emergentintegrations", "EMERGENT_LLM_KEY", "status_checks"):
        assert forbidden not in source, f"identity service still references {forbidden}"


def test_the_gateway_routes_each_prefix_to_its_owner():
    prefixes = _nginx_prefixes()
    assert prefixes.get("/api/auth/") == "identity" and prefixes.get("/api/shortlists") == "identity"
    assert prefixes.get("/api/") == "api"
    # nothing the analytics API serves may sit under a prefix the gateway sends to the identity service
    shadowed = [p for p in _api_routes() if p.startswith(("/api/auth/", "/api/shortlists"))]
    assert not shadowed, f"API routes unreachable behind the gateway: {shadowed}"


def _frontend_paths() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in FRONTEND_SRC.rglob("*.js"):
        for m in re.finditer(r"[`'\"]((?:\$\{[A-Za-z_.]+\})?/api/[^`'\"?\s]*)", path.read_text(encoding="utf-8")):
            raw = re.sub(r"^\$\{[A-Za-z_.]+\}", "", m.group(1))
            raw = re.sub(r"\$\{[^}]*\}", "x", raw).rstrip("/")
            found.setdefault(raw or "/", set()).add(path.name)
    return found


def test_every_frontend_api_path_exists_on_the_backend_that_owns_it():
    backend = [p for p in _api_routes() | _identity_routes()]
    patterns = [re.compile("^" + re.sub(r"\\\{[^}]*\\\}", "[^/]+", re.escape(p)) + "$") for p in backend]
    missing = {}
    for path, files in _frontend_paths().items():
        if any(p.fullmatch(path) for p in patterns):
            continue
        if any(b.startswith(path + "/") for b in backend):  # a base prefix that sub-paths are appended to
            continue
        missing[path] = sorted(files)
    assert not missing, f"frontend calls with no backend route: {missing}"
