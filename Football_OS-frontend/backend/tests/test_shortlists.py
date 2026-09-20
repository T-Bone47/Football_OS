"""Live regression tests for /api/shortlists CRUD + share + public read."""
import os
import re
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env", encoding="utf-8") as f:
        BASE_URL = next(l.split("=", 1)[1].strip() for l in f if l.startswith("REACT_APP_BACKEND_URL="))
BASE_URL = BASE_URL.rstrip("/")

PRIMARY_TOKEN = "test_ui_football_token"
PRIMARY_USER = "test_ui_football"


@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


@pytest.fixture(scope="module", autouse=True)
def ensure_primary(mongo_db):
    """Ensure primary seeded session exists."""
    mongo_db.users.update_one(
        {"user_id": PRIMARY_USER},
        {"$set": {"user_id": PRIMARY_USER, "email": "scout@football-os.test", "name": "Test Scout", "picture": None}},
        upsert=True,
    )
    mongo_db.user_sessions.update_one(
        {"session_token": PRIMARY_TOKEN},
        {"$set": {"user_id": PRIMARY_USER, "session_token": PRIMARY_TOKEN,
                  "expires_at": datetime.now(timezone.utc) + timedelta(hours=6)}},
        upsert=True,
    )
    yield
    # cleanup any TEST_ shortlists this run created
    mongo_db.shortlists.delete_many({"name": {"$regex": "^TEST_"}})


@pytest.fixture(scope="module")
def secondary_session(mongo_db):
    suffix = uuid.uuid4().hex[:8]
    uid = f"TEST_second_{suffix}"
    tok = f"TEST_secondtok_{suffix}"
    mongo_db.users.insert_one({"user_id": uid, "email": f"TEST_{suffix}@x.test", "name": "Other User", "picture": None})
    mongo_db.user_sessions.insert_one({"user_id": uid, "session_token": tok,
                                       "expires_at": datetime.now(timezone.utc) + timedelta(hours=1)})
    yield tok
    mongo_db.user_sessions.delete_many({"user_id": uid})
    mongo_db.users.delete_many({"user_id": uid})


def auth(t):
    return {"Authorization": f"Bearer {t}"}


# ---------- Auth gating ----------
def test_list_requires_auth():
    r = requests.get(f"{BASE_URL}/api/shortlists", timeout=15)
    assert r.status_code == 401


def test_create_requires_auth():
    r = requests.post(f"{BASE_URL}/api/shortlists", json={"name": "x", "tags": []}, timeout=15)
    assert r.status_code == 401


# ---------- Core CRUD ----------
def test_full_shortlist_lifecycle(mongo_db):
    # CREATE
    payload = {"name": f"TEST_lifecycle_{uuid.uuid4().hex[:6]}", "tags": ["cb", "u21"], "notes": "seed"}
    r = requests.post(f"{BASE_URL}/api/shortlists", headers=auth(PRIMARY_TOKEN), json=payload, timeout=15)
    assert r.status_code == 200, r.text
    board = r.json()
    assert board["name"] == payload["name"]
    assert board["tags"] == ["cb", "u21"]
    assert board["owner_user_id"] == PRIMARY_USER
    assert board["id"].startswith("sl_")
    assert "_id" not in board
    sid = board["id"]

    # LIST
    r = requests.get(f"{BASE_URL}/api/shortlists", headers=auth(PRIMARY_TOKEN), timeout=15)
    assert r.status_code == 200
    assert any(b["id"] == sid for b in r.json())

    # GET single
    r = requests.get(f"{BASE_URL}/api/shortlists/{sid}", headers=auth(PRIMARY_TOKEN), timeout=15)
    assert r.status_code == 200 and r.json()["id"] == sid

    # PATCH rename+retag
    r = requests.patch(f"{BASE_URL}/api/shortlists/{sid}", headers=auth(PRIMARY_TOKEN),
                       json={"name": payload["name"] + "_renamed", "tags": ["gk"]}, timeout=15)
    assert r.status_code == 200
    assert r.json()["name"].endswith("_renamed")
    assert r.json()["tags"] == ["gk"]
    # verify persistence via GET
    r = requests.get(f"{BASE_URL}/api/shortlists/{sid}", headers=auth(PRIMARY_TOKEN), timeout=15)
    assert r.json()["tags"] == ["gk"]

    # ADD PLAYER
    p = {"id": "p_test_1", "name": "TEST Player", "position": "CB", "club": "TEST FC"}
    r = requests.post(f"{BASE_URL}/api/shortlists/{sid}/players", headers=auth(PRIMARY_TOKEN), json=p, timeout=15)
    assert r.status_code == 200
    assert len(r.json()["players"]) == 1

    # DUPLICATE 409
    r = requests.post(f"{BASE_URL}/api/shortlists/{sid}/players", headers=auth(PRIMARY_TOKEN), json=p, timeout=15)
    assert r.status_code == 409

    # REMOVE PLAYER
    r = requests.delete(f"{BASE_URL}/api/shortlists/{sid}/players/p_test_1",
                        headers=auth(PRIMARY_TOKEN), timeout=15)
    assert r.status_code == 200
    assert r.json()["players"] == []

    # SHARE
    r = requests.post(f"{BASE_URL}/api/shortlists/{sid}/share", headers=auth(PRIMARY_TOKEN), timeout=15)
    assert r.status_code == 200
    token1 = r.json()["share_token"]
    assert token1 and token1.startswith("tok_")
    assert re.match(r"^tok_[a-f0-9]{32}$", token1)
    assert r.json()["is_shared"] is True

    # PUBLIC READ - no auth
    r = requests.get(f"{BASE_URL}/api/shortlists/shared/{token1}", timeout=15)
    assert r.status_code == 200, r.text
    shared = r.json()
    assert shared["id"] == sid
    assert shared["name"].endswith("_renamed")
    assert "owner_name" in shared
    assert "_id" not in shared

    # RE-SHARE rotates token
    r = requests.post(f"{BASE_URL}/api/shortlists/{sid}/share", headers=auth(PRIMARY_TOKEN), timeout=15)
    token2 = r.json()["share_token"]
    assert token2 != token1
    # old token now 404
    r = requests.get(f"{BASE_URL}/api/shortlists/shared/{token1}", timeout=15)
    assert r.status_code == 404

    # UNSHARE
    r = requests.delete(f"{BASE_URL}/api/shortlists/{sid}/share", headers=auth(PRIMARY_TOKEN), timeout=15)
    assert r.status_code == 200
    r = requests.get(f"{BASE_URL}/api/shortlists/shared/{token2}", timeout=15)
    assert r.status_code == 404

    # DELETE
    r = requests.delete(f"{BASE_URL}/api/shortlists/{sid}", headers=auth(PRIMARY_TOKEN), timeout=15)
    assert r.status_code == 200
    r = requests.get(f"{BASE_URL}/api/shortlists/{sid}", headers=auth(PRIMARY_TOKEN), timeout=15)
    assert r.status_code == 404


# ---------- Authorization isolation ----------
def test_other_user_cannot_access(secondary_session):
    # primary creates
    r = requests.post(f"{BASE_URL}/api/shortlists", headers=auth(PRIMARY_TOKEN),
                      json={"name": f"TEST_iso_{uuid.uuid4().hex[:6]}", "tags": []}, timeout=15)
    sid = r.json()["id"]
    try:
        # secondary GET -> 404
        r = requests.get(f"{BASE_URL}/api/shortlists/{sid}", headers=auth(secondary_session), timeout=15)
        assert r.status_code == 404
        # secondary DELETE -> 404
        r = requests.delete(f"{BASE_URL}/api/shortlists/{sid}", headers=auth(secondary_session), timeout=15)
        assert r.status_code == 404
        # secondary LIST empty (or no sid)
        r = requests.get(f"{BASE_URL}/api/shortlists", headers=auth(secondary_session), timeout=15)
        assert r.status_code == 200
        assert not any(b["id"] == sid for b in r.json())
    finally:
        requests.delete(f"{BASE_URL}/api/shortlists/{sid}", headers=auth(PRIMARY_TOKEN), timeout=15)


def test_shared_invalid_token_404():
    r = requests.get(f"{BASE_URL}/api/shortlists/shared/tok_nonexistent_xxx", timeout=15)
    assert r.status_code == 404
