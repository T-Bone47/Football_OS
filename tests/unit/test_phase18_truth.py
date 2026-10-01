"""Phase 18 — no invented content outside DEV_SEED (R10, N1).

The legacy Phase 10-16 engines used to fill themselves with invented players,
outcomes, alerts and research at import time. These tests construct every
such engine with DEV_SEED off and fail if any seed routine runs or any engine
starts with content. The rest of the legacy suite runs with DEV_SEED=true
(tests/conftest.py) and exercises engine logic on those labelled fixtures.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

from app.config import Settings

LEGACY_PACKAGES = ["app.phase10", "app.phase11", "app.phase12", "app.phase13", "app.phase14", "app.phase15",
                   "app.phase16"]


@pytest.fixture
def seeds_off(monkeypatch):
    import app.dev_fixtures as fx
    monkeypatch.setattr(fx, "get_settings", lambda: Settings(dev_seed=False, environment="development"))
    yield


def _legacy_modules():
    for pkg_name in LEGACY_PACKAGES:
        pkg = importlib.import_module(pkg_name)
        for info in pkgutil.iter_modules(pkg.__path__):
            yield importlib.import_module(f"{pkg_name}.{info.name}")


def _seeding_classes():
    for mod in _legacy_modules():
        for name, cls in inspect.getmembers(mod, inspect.isclass):
            if cls.__module__ == mod.__name__ and any(a.startswith("_seed") for a in vars(cls)):
                yield cls


SEEDING_CLASSES = sorted({c for c in _seeding_classes()}, key=lambda c: f"{c.__module__}.{c.__name__}")


def test_seeding_classes_were_found():
    # Guards the parametrised test below against silently testing nothing.
    assert len(SEEDING_CLASSES) >= 39


@pytest.mark.parametrize("cls", SEEDING_CLASSES, ids=lambda c: f"{c.__module__.split('.', 1)[1]}.{c.__name__}")
def test_engine_never_seeds_without_dev_seed(cls, seeds_off, monkeypatch):
    for attr in [a for a in vars(cls) if a.startswith("_seed")]:
        def _boom(*_a, _attr=attr, **_k):
            raise AssertionError(f"{cls.__name__}.{_attr} ran without DEV_SEED")
        monkeypatch.setattr(cls, attr, _boom)
    sig = inspect.signature(cls.__init__)
    required = [p for p in list(sig.parameters.values())[1:]
                if p.default is inspect.Parameter.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
    if required:
        pytest.skip(f"constructor needs {[p.name for p in required]}")
    cls()


GETTER_MODULES = [
    ("app.phase15.experiment_engine", "get_experiment_engine"),
    ("app.phase15.league_translation", "get_league_translation_engine"),
    ("app.phase15.tactical_pattern_research", "get_tactical_pattern_engine"),
    ("app.phase15.adaptive_candidates", "get_adaptive_model_engine"),
    ("app.phase15.feature_discovery", "get_feature_discovery_engine"),
    ("app.phase15.research_questions", "get_question_registry"),
    ("app.phase15.hypothesis_governance", "get_hypothesis_engine"),
    ("app.phase15.cohort_engine", "get_cohort_engine"),
    ("app.phase15.pattern_discovery", "get_pattern_discovery_engine"),
    ("app.phase15.transfer_market_research", "get_transfer_market_engine"),
    ("app.phase16.background_jobs", "get_job_manager"),
    ("app.phase16.freshness_engine", "get_freshness_engine"),
    ("app.phase16.data_quality_engine", "get_data_quality_engine"),
    ("app.phase16.alerting_engine", "get_alerting_engine"),
    ("app.phase16.audit_logger", "get_audit_logger"),
]


def _is_empty(engine) -> bool:
    for value in vars(engine).values():
        if isinstance(value, (dict, list, set, tuple)) and len(value) > 0:
            return False
    return True


@pytest.mark.parametrize("module_name,getter", GETTER_MODULES)
def test_singleton_getter_starts_empty_without_dev_seed(module_name, getter, seeds_off, monkeypatch):
    mod = importlib.import_module(module_name)
    global_names = [n for n in vars(mod) if n.startswith("_GLOBAL_")]
    assert global_names, f"{module_name} has no singleton"
    for n in global_names:
        monkeypatch.setattr(mod, n, None)
    engine = getattr(mod, getter)()
    non_empty = {k: type(v).__name__ for k, v in vars(engine).items()
                 if isinstance(v, (dict, list, set, tuple)) and len(v) > 0}
    assert _is_empty(engine), f"{getter}() created content without DEV_SEED: {non_empty}"


def test_dev_seed_defaults_off_and_is_ignored_in_hardened_environments(monkeypatch):
    import app.dev_fixtures as fx
    monkeypatch.delenv("DEV_SEED", raising=False)  # the test process opts in; the default must not
    monkeypatch.setattr(fx, "get_settings", lambda: Settings(_env_file=None, environment="development"))
    assert fx.dev_seed_enabled() is False
    for env in ("staging", "production"):
        monkeypatch.setattr(fx, "get_settings", lambda env=env: Settings(dev_seed=True, environment=env))
        assert fx.dev_seed_enabled() is False


def test_startup_refuses_dev_seed_in_production():
    from app.phase17.environments import audit_environment
    s = Settings(environment="production", dev_seed=True, database_url="postgresql+asyncpg://u:strong-pw@db:5432/x",
                 cors_allowed_origins="https://app.example.com", snapshot_storage_backend="s3",
                 s3_secret_key="not-a-default-secret", s3_bucket="fios-production")
    audit = audit_environment(s)
    assert any("DEV_SEED" in v for v in audit.violations)
