import pytest

from app.providers.registry import ProviderRegistry
from app.providers.statsbomb import StatsBombProvider


def test_get_returns_instance_from_registered_factory():
    registry = ProviderRegistry()
    registry.register("statsbomb", StatsBombProvider)

    provider = registry.get("statsbomb")

    assert isinstance(provider, StatsBombProvider)
    assert provider.name == "statsbomb"


def test_get_unknown_provider_raises_with_known_list():
    registry = ProviderRegistry()
    registry.register("statsbomb", StatsBombProvider)

    with pytest.raises(KeyError, match="statsbomb"):
        registry.get("not-a-real-provider")


def test_default_registry_knows_only_active_providers():
    from app.providers.registry import default_registry

    assert default_registry.known_providers() == ["api-football", "statsbomb"]


def test_football_data_org_not_active_by_default_but_registerable():
    from app.providers.football_data_org import FootballDataOrgProvider
    from app.providers.registry import ProviderRegistry, register_optional_providers

    registry = ProviderRegistry()
    with pytest.raises(KeyError):
        registry.get("football-data-org")

    register_optional_providers(registry)

    assert "football-data-org" in registry.known_providers()
    # register_optional_providers wired up the right factory — checked
    # directly rather than instantiating (that needs a real token, and is
    # covered separately in test_provider_protocol.py).
    assert registry._factories["football-data-org"] is FootballDataOrgProvider
