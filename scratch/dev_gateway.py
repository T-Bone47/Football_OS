"""Local development gateway for Football Intelligence OS.

The browser needs ONE origin, but this project has TWO backends
(docs/ADR-0004-backend-ownership-and-gateway.md):

    /api/auth/*, /api/shortlists*  -> identity service (MongoDB)
    everything else under /api/*   -> analytics API (PostgreSQL)

This is a thin reverse proxy implementing exactly that ownership table. It also
exposes a clearly-labelled dev-only sign-in helper (`/dev/sign-in`) that drops
the same session cookie a real Google sign-in would, so the local UI can be
opened without the external OAuth round-trip. It does not touch the app's
authentication code and is not intended for anything but local use.

Run:  uvicorn dev_gateway:app --port 8004
"""
from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse

IDENTITY_URL = os.environ.get("FIOS_IDENTITY_URL", "http://127.0.0.1:8003").rstrip("/")
API_URL = os.environ.get("FIOS_API_URL", "http://127.0.0.1:8002").rstrip("/")
DEV_SESSION_TOKEN = os.environ.get("FIOS_DEV_SESSION_TOKEN", "local_dev_session_token_9f3c1a")
FRONTEND_ORIGIN = os.environ.get("FIOS_FRONTEND_ORIGIN", "http://localhost:3005")

app = FastAPI(title="Football Intelligence OS (local dev gateway)", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Hop-by-hop headers are meaningless end-to-end; the upstream CORS headers are
# replaced by this gateway's own so the browser sees one consistent origin.
_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}
_CORS = {
    "access-control-allow-origin", "access-control-allow-credentials",
    "access-control-allow-methods", "access-control-allow-headers",
    "access-control-expose-headers", "access-control-max-age",
}

_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0))


@app.on_event("shutdown")
async def _close() -> None:
    await _client.aclose()


def _owner(path: str) -> str:
    """URL-prefix ownership per ADR-0004: identity owns auth + shortlists, API owns the rest."""
    if path == "/api/auth" or path.startswith("/api/auth/") or path.startswith("/api/shortlists"):
        return IDENTITY_URL
    return API_URL


@app.get("/dev/sign-in", include_in_schema=False)
def dev_sign_in() -> RedirectResponse:
    """Dev helper: drop the seeded session cookie, then open the app on the UI origin."""
    resp = RedirectResponse(url=f"{FRONTEND_ORIGIN}/dashboard", status_code=302)
    resp.set_cookie("session_token", DEV_SESSION_TOKEN, max_age=7 * 24 * 3600, path="/", samesite="lax")
    return resp


@app.get("/dev/sign-out", include_in_schema=False)
def dev_sign_out() -> RedirectResponse:
    resp = RedirectResponse(url=f"{FRONTEND_ORIGIN}/login", status_code=302)
    resp.delete_cookie("session_token", path="/")
    return resp


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy(path: str, request: Request) -> StreamingResponse:
    target = _owner("/" + path)
    url = f"{target}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
    body = await request.body()
    upstream_req = _client.build_request(request.method, url, headers=headers, content=body)
    upstream = await _client.send(upstream_req, stream=True)

    resp_headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in _HOP and k.lower() not in _CORS
    }

    async def _stream():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        _stream(),
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )
