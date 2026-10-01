"""The one switch for demo fixtures (Phase 18, R10 / N1).

Phases 10-16 built engines that filled themselves with invented football
content at import time: players, trajectories, outcomes, alerts, research
cohorts, squads. None of it was observed data. Those fixtures now load only
when DEV_SEED=true *and* the environment is not staging or production; the
startup policy refuses DEV_SEED in hardened environments. Without the flag
every engine starts empty and its routes return empty results.
"""
from __future__ import annotations

from app.config import get_settings
from app.phase17.environments import is_hardened, resolve_environment

# Label carried by anything a demo fixture produced, so it can never be read
# as observed data.
DEMO_FIXTURE = "DEV_SEED_DEMO_FIXTURE"


def dev_seed_enabled() -> bool:
    settings = get_settings()
    if not getattr(settings, "dev_seed", False):
        return False
    return not is_hardened(resolve_environment(settings.environment))
