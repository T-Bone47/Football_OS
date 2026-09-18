"""Provider registry (architecture doc §20): callers ask the registry for a
provider by name instead of an if/elif chain scattered through the app.
Lazy factories — instantiating ApiFootballProvider (which needs a key) only
happens when something actually requests it.
"""
from __future__ import annotations

from collections.abc import Callable

from app.providers.api_football import ApiFootballProvider
from app.providers.base import FootballDataProvider
from app.providers.football_data_org import FootballDataOrgProvider
from app.providers.statsbomb import StatsBombProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], FootballDataProvider]] = {}

    def register(self, name: str, factory: Callable[[], FootballDataProvider]) -> None:
        self._factories[name] = factory

    def get(self, name: str) -> FootballDataProvider:
        if name not in self._factories:
            known = ", ".join(sorted(self._factories)) or "(none registered)"
            raise KeyError(f"No provider registered as '{name}'. Known providers: {known}")
        return self._factories[name]()

    def known_providers(self) -> list[str]:
        return sorted(self._factories)


def build_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("statsbomb", StatsBombProvider)
    registry.register("api-football", ApiFootballProvider)
    registry.register("football-data-org", FootballDataOrgProvider)
    return registry


default_registry = build_default_registry()
