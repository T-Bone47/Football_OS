"""Provider registry (architecture doc §20): callers ask the registry for a
provider by name instead of an if/elif chain scattered through the app.
Lazy factories — instantiating ApiFootballProvider (which needs a key) only
happens when something actually requests it.

Active vs. optional (provider-finalization phase): `default_registry` only
auto-registers the CURRENTLY ACTIVE providers. football-data.org's adapter
is fully implemented and still registerable — see
`register_optional_providers()` — it's just not wired in by default while
API-Football is the only enabled provider. This is a registration-time
distinction, not a deletion: the generic register()/get() interface doesn't
know or care which providers are "active".
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
    """Active providers only. See ADR-008 for why football-data.org isn't here."""
    registry = ProviderRegistry()
    registry.register("statsbomb", StatsBombProvider)
    registry.register("api-football", ApiFootballProvider)
    return registry


def register_optional_providers(registry: ProviderRegistry) -> None:
    """Re-enable providers that exist and work but aren't active by default.
    Call this explicitly (e.g. registry.register(..) directly, or this
    helper for all of them) when you actually want football-data.org back —
    nothing about the adapter itself changed, it's still real, tested code.
    """
    registry.register("football-data-org", FootballDataOrgProvider)


default_registry = build_default_registry()
