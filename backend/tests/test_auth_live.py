"""Live regression checks for managed session authentication."""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient
from urllib.parse import urlparse

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env", encoding="utf-8") as env_file:
        BASE_URL = next(line.split("=", 1)[1].strip() for line in env_file if line.startswith("REACT_APP_BACKEND_URL="))
BASE_URL = BASE_URL.rstrip("/")
COOKIE_DOMAIN = urlparse(BASE_URL).hostname


@pytest.fixture
def seeded_session():
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    suffix = uuid.uuid4().hex
    user_id = f"TEST_auth_{suffix}"
    token = f"TEST_token_{suffix}"
    db.users.insert_one({"user_id": user_id, "email": f"TEST_{suffix}@example.com", "name": "TEST Auth User", "picture": None})
    db.user_sessions.insert_one({"user_id": user_id, "session_token": token, "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)})
    yield token
    db.user_sessions.delete_many({"session_token": token})
    db.users.delete_many({"user_id": user_id})
    mongo.close()


def test_auth_me_bearer_excludes_mongo_id(seeded_session):
    response = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {seeded_session}"}, timeout=20)
    assert response.status_code == 200
    body = response.json()
    assert body["email"].startswith("TEST_")
    assert body["user_id"].startswith("TEST_auth_")
    assert "_id" not in body


def test_auth_me_cookie_and_logout(seeded_session):
    session = requests.Session()
    session.cookies.set("session_token", seeded_session, domain=COOKIE_DOMAIN, path="/")
    response = session.get(f"{BASE_URL}/api/auth/me", timeout=20)
    assert response.status_code == 200
    assert response.json()["name"] == "TEST Auth User"
    logout = session.post(f"{BASE_URL}/api/auth/logout", timeout=20)
    assert logout.status_code == 200
    assert session.get(f"{BASE_URL}/api/auth/me", timeout=20).status_code == 401