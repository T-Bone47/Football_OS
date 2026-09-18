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


def test_default_registry_knows_all_three_providers():
    from app.providers.registry import default_registry

    assert default_registry.known_providers() == ["api-football", "football-data-org", "statsbomb"]
