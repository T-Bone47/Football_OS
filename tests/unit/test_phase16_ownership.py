"""Object-level authorization for Phase 16 projects/watchlists (R10): org scoping, owner-only, no seeds, no overwrite."""
from __future__ import annotations

import pytest

from app.phase16.projects_and_auth import DuplicateIdError, ProjectAndAuthManager
from app.security.tokens import Principal

ALICE = Principal(user_id="alice", roles=frozenset({"scout"}), org_id="org_a")
ALICE_COLLEAGUE = Principal(user_id="amy", roles=frozenset({"analyst"}), org_id="org_a")
BOB = Principal(user_id="bob", roles=frozenset({"scout"}), org_id="org_b")
NO_ORG = Principal(user_id="solo", roles=frozenset({"scout"}), org_id=None)


def _mgr() -> ProjectAndAuthManager:
    mgr = ProjectAndAuthManager()
    mgr.create_project("p1", "org_a", "Winger search", "d", "FW", "Inside Forward", lead_scout_id="alice")
    mgr.create_watchlist("w1", "alice", "org_a", "Alice's list")
    return mgr


def test_a_fresh_manager_contains_no_seeded_users_projects_or_watchlists():
    mgr = ProjectAndAuthManager()
    for who in (ALICE, BOB, NO_ORG):
        assert mgr.list_projects_for(who) == [] and mgr.list_watchlists_for(who) == []


def test_projects_are_visible_to_their_organisation_only():
    mgr = _mgr()
    assert [p.project_id for p in mgr.list_projects_for(ALICE_COLLEAGUE)] == ["p1"]
    assert mgr.list_projects_for(BOB) == []
    with pytest.raises(KeyError):  # 404, not 403: existence is not leaked across tenants
        mgr.get_project_for(BOB, "p1")


def test_the_lead_scout_keeps_access_without_an_org_claim():
    mgr = ProjectAndAuthManager()
    mgr.create_project("p2", "org_a", "n", "d", "FW", "r", lead_scout_id="solo")
    assert mgr.get_project_for(NO_ORG, "p2").project_id == "p2"
    with pytest.raises(KeyError):
        mgr.get_project_for(Principal(user_id="x", roles=frozenset(), org_id=None), "p2")


def test_watchlists_are_private_to_their_owner_even_inside_the_same_org():
    mgr = _mgr()
    assert [w.watchlist_id for w in mgr.list_watchlists_for(ALICE)] == ["w1"]
    assert mgr.list_watchlists_for(ALICE_COLLEAGUE) == [] and mgr.list_watchlists_for(BOB) == []
    for intruder in (ALICE_COLLEAGUE, BOB):
        with pytest.raises(KeyError):
            mgr.get_watchlist_for(intruder, "w1")


def test_client_supplied_ids_never_overwrite_existing_objects():
    mgr = _mgr()
    with pytest.raises(DuplicateIdError):
        mgr.create_project("p1", "org_b", "hijack", "d", "FW", "r", lead_scout_id="bob")
    with pytest.raises(DuplicateIdError):
        mgr.create_watchlist("w1", "bob", "org_b", "hijack")
    assert mgr.get_project("p1").organization_id == "org_a" and mgr.get_watchlist("w1").user_id == "alice"
