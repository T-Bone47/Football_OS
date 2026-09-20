"""Live regression checks for /api/copilot/query SSE streaming (Claude Sonnet 5)."""
import json
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env", encoding="utf-8") as env_file:
        BASE_URL = next(line.split("=", 1)[1].strip() for line in env_file if line.startswith("REACT_APP_BACKEND_URL="))
BASE_URL = BASE_URL.rstrip("/")

SEEDED_TOKEN = "test_ui_football_token"


def test_copilot_requires_auth():
    r = requests.post(
        f"{BASE_URL}/api/copilot/query",
        json={"session_id": "s1", "query": "hi", "context_players": []},
        timeout=20,
    )
    assert r.status_code == 401


def test_copilot_streams_tokens_authenticated():
    headers = {"Authorization": f"Bearer {SEEDED_TOKEN}"}
    payload = {
        "session_id": "test-copilot-stream",
        "query": "Give a brief overview of how the platform surfaces recruitment candidates.",
        "context_players": [],
    }
    with requests.post(
        f"{BASE_URL}/api/copilot/query",
        json=payload,
        headers=headers,
        stream=True,
        timeout=60,
    ) as r:
        assert r.status_code == 200, r.text
        assert "text/event-stream" in r.headers.get("content-type", "")
        deltas = []
        got_done = False
        got_error = None
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            if raw.startswith("data:"):
                try:
                    payload = json.loads(raw[5:].strip())
                except json.JSONDecodeError:
                    continue
                if "delta" in payload:
                    deltas.append(payload["delta"])
                if payload.get("done"):
                    got_done = True
                    break
                if "error" in payload:
                    got_error = payload["error"]
                    break
        assert got_error is None, f"Copilot stream error: {got_error}"
        assert got_done, "Stream did not signal completion"
        assert len("".join(deltas)) > 20, f"Expected streamed content, got: {deltas!r}"
