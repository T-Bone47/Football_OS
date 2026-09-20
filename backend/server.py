from fastapi import FastAPI, APIRouter, Cookie, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from typing import List, Optional, Any
import uuid
import json
from datetime import datetime, timezone, timedelta
import requests
import asyncio


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")


class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: str | None = None


class SessionExchange(BaseModel):
    user: User


class SessionExchangeRequest(BaseModel):
    session_id: str = Field(min_length=1)


class ProviderIdentity(BaseModel):
    email: str
    session_token: str = Field(min_length=1)
    name: str | None = None
    picture: str | None = None


class CopilotContextPlayer(BaseModel):
    id: Optional[str] = None
    name: str
    primary_position: Optional[str] = None
    nationality: Optional[str] = None


class CopilotRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=2000)
    context_players: List[CopilotContextPlayer] = Field(default_factory=list)


class ShortlistPlayer(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    primary_position: Optional[str] = None
    nationality: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=400)
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ShortlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=1000)
    tags: List[str] = Field(default_factory=list)


class ShortlistUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[List[str]] = None


class ShortlistPlayerCreate(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    primary_position: Optional[str] = None
    nationality: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=400)


class Shortlist(BaseModel):
    id: str
    owner_user_id: str
    owner_name: Optional[str] = None
    name: str
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    players: List[ShortlistPlayer] = Field(default_factory=list)
    share_token: Optional[str] = None
    is_shared: bool = False
    created_at: datetime
    updated_at: datetime


class SharedShortlist(BaseModel):
    id: str
    owner_name: Optional[str] = None
    name: str
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    players: List[ShortlistPlayer] = Field(default_factory=list)
    updated_at: datetime


@api_router.get("/")
async def root():
    return {"message": "Football Intelligence OS API"}


def _session_token(request: Request, authorization: str | None) -> str | None:
    cookie_token = request.cookies.get("session_token")
    if cookie_token:
        return cookie_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def _user_for_session(request: Request, authorization: str | None) -> dict:
    token = _session_token(request, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Session not found")
    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        await db.user_sessions.delete_one({"session_token": token})
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@api_router.post("/auth/session", response_model=SessionExchange)
async def exchange_session(payload: SessionExchangeRequest, response: Response):
    session_id = payload.session_id
    try:
        session_response = await asyncio.to_thread(
            requests.get,
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id},
            timeout=15,
        )
        session_response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Google session exchange failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not complete Google sign-in") from exc
    try:
        identity = ProviderIdentity.model_validate(session_response.json())
    except (ValidationError, ValueError) as exc:
        logger.warning("Google provider returned an invalid identity payload")
        raise HTTPException(status_code=502, detail="Google sign-in returned incomplete account data") from exc
    identity_data = identity.model_dump()
    user = await db.users.find_one({"email": identity.email}, {"_id": 0})
    if user:
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"name": identity.name or user["name"], "picture": identity.picture}},
        )
        user.update({"name": identity.name or user["name"], "picture": identity.picture})
    else:
        user = {
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": identity.email,
            "name": identity.name or identity.email,
            "picture": identity.picture,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
        user = {key: value for key, value in user.items() if key != "created_at"}
    session_token = identity_data["session_token"]
    await db.user_sessions.delete_many({"user_id": user["user_id"]})
    await db.user_sessions.insert_one({
        "user_id": user["user_id"],
        "session_token": session_token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": datetime.now(timezone.utc),
    })
    response.set_cookie("session_token", session_token, max_age=7 * 24 * 60 * 60, httponly=True, secure=True, samesite="none", path="/")
    return {"user": User(**user)}


@api_router.get("/auth/me", response_model=User)
async def get_current_user(request: Request, authorization: str | None = Header(default=None)):
    return await _user_for_session(request, authorization)


@api_router.post("/auth/logout")
async def logout(request: Request, response: Response, authorization: str | None = Header(default=None)):
    token = _session_token(request, authorization)
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


COPILOT_SYSTEM = (
    "You are the Scout Copilot for Football Intelligence OS, an evidence-driven football "
    "recruitment platform. You NEVER invent player statistics, market values, or transfer "
    "predictions. When a user asks for candidates, you (1) restate the criteria you detected, "
    "(2) explain the analytical approach the platform would take (role fit, similarity, "
    "valuation, transfer risk), and (3) surface only players that were provided to you in "
    "the structured context; if none were provided you say the connected data source has "
    "not been supplied yet and list the endpoints the platform would query. Keep answers "
    "concise, professional, and calibrated: distinguish FACT, MODEL OUTPUT, and ESTIMATE. "
    "Never present a prediction as a certainty."
)


@api_router.post("/copilot/query")
async def copilot_query(request: Request, payload: CopilotRequest, authorization: str | None = Header(default=None)):
    await _user_for_session(request, authorization)
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Copilot is not configured on this environment.")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
    except ImportError as exc:
        logger.exception("emergentintegrations import failed")
        raise HTTPException(status_code=503, detail="Copilot library is unavailable.") from exc

    context_lines = []
    if payload.context_players:
        context_lines.append("Connected data context (players supplied by the Football Intelligence OS API):")
        for entry in payload.context_players[:20]:
            context_lines.append(
                f"- {entry.name} · {entry.primary_position or 'position unknown'} · {entry.nationality or 'nationality unknown'}"
            )
    else:
        context_lines.append("Connected data context: none — the live Football Intelligence OS API has not returned player rows yet.")

    prompt = f"Question: {payload.query.strip()}\n\n" + "\n".join(context_lines)

    async def event_generator():
        chat = LlmChat(
            api_key=api_key,
            session_id=payload.session_id,
            system_message=COPILOT_SYSTEM,
        ).with_model("anthropic", "claude-sonnet-5")
        try:
            async for event in chat.stream_message(UserMessage(text=prompt)):
                if isinstance(event, TextDelta):
                    yield f"data: {json.dumps({'delta': event.content})}\n\n"
                elif isinstance(event, StreamDone):
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    break
        except Exception as exc:  # noqa: BLE001
            logger.exception("Copilot stream error")
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    _ = await db.status_checks.insert_one(doc)
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    return status_checks


# ============================================================
# SHORTLISTS
# ============================================================

def _serialize_shortlist(doc: dict) -> dict:
    doc = {k: v for k, v in doc.items() if k != "_id"}
    for key in ("created_at", "updated_at"):
        if isinstance(doc.get(key), str):
            doc[key] = datetime.fromisoformat(doc[key])
    for player in doc.get("players", []):
        if isinstance(player.get("added_at"), str):
            player["added_at"] = datetime.fromisoformat(player["added_at"])
    doc["is_shared"] = bool(doc.get("share_token"))
    return doc


@api_router.get("/shortlists", response_model=List[Shortlist])
async def list_shortlists(request: Request, authorization: str | None = Header(default=None)):
    user = await _user_for_session(request, authorization)
    docs = await db.shortlists.find({"owner_user_id": user["user_id"]}).sort("updated_at", -1).to_list(200)
    return [_serialize_shortlist(d) for d in docs]


@api_router.post("/shortlists", response_model=Shortlist)
async def create_shortlist(payload: ShortlistCreate, request: Request, authorization: str | None = Header(default=None)):
    user = await _user_for_session(request, authorization)
    now = datetime.now(timezone.utc)
    doc = {
        "id": f"sl_{uuid.uuid4().hex[:12]}",
        "owner_user_id": user["user_id"],
        "owner_name": user.get("name"),
        "name": payload.name.strip(),
        "notes": (payload.notes or "").strip() or None,
        "tags": [t.strip() for t in payload.tags if t.strip()][:12],
        "players": [],
        "share_token": None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    await db.shortlists.insert_one(doc)
    return _serialize_shortlist(doc)


@api_router.get("/shortlists/{shortlist_id}", response_model=Shortlist)
async def get_shortlist(shortlist_id: str, request: Request, authorization: str | None = Header(default=None)):
    user = await _user_for_session(request, authorization)
    doc = await db.shortlists.find_one({"id": shortlist_id, "owner_user_id": user["user_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Shortlist not found")
    return _serialize_shortlist(doc)


@api_router.patch("/shortlists/{shortlist_id}", response_model=Shortlist)
async def update_shortlist(shortlist_id: str, payload: ShortlistUpdate, request: Request, authorization: str | None = Header(default=None)):
    user = await _user_for_session(request, authorization)
    updates: dict = {}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
    if payload.notes is not None:
        updates["notes"] = payload.notes.strip() or None
    if payload.tags is not None:
        updates["tags"] = [t.strip() for t in payload.tags if t.strip()][:12]
    if not updates:
        raise HTTPException(status_code=400, detail="No changes supplied")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.shortlists.find_one_and_update(
        {"id": shortlist_id, "owner_user_id": user["user_id"]},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Shortlist not found")
    return _serialize_shortlist(result)


@api_router.delete("/shortlists/{shortlist_id}")
async def delete_shortlist(shortlist_id: str, request: Request, authorization: str | None = Header(default=None)):
    user = await _user_for_session(request, authorization)
    result = await db.shortlists.delete_one({"id": shortlist_id, "owner_user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Shortlist not found")
    return {"ok": True}


@api_router.post("/shortlists/{shortlist_id}/players", response_model=Shortlist)
async def add_shortlist_player(shortlist_id: str, payload: ShortlistPlayerCreate, request: Request, authorization: str | None = Header(default=None)):
    user = await _user_for_session(request, authorization)
    doc = await db.shortlists.find_one({"id": shortlist_id, "owner_user_id": user["user_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Shortlist not found")
    if any(p.get("id") == payload.id for p in doc.get("players", [])):
        raise HTTPException(status_code=409, detail="Player is already in this shortlist")
    player_entry = {
        **payload.model_dump(),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    now = datetime.now(timezone.utc).isoformat()
    result = await db.shortlists.find_one_and_update(
        {"id": shortlist_id, "owner_user_id": user["user_id"]},
        {"$push": {"players": player_entry}, "$set": {"updated_at": now}},
        return_document=True,
    )
    return _serialize_shortlist(result)


@api_router.delete("/shortlists/{shortlist_id}/players/{player_id}", response_model=Shortlist)
async def remove_shortlist_player(shortlist_id: str, player_id: str, request: Request, authorization: str | None = Header(default=None)):
    user = await _user_for_session(request, authorization)
    now = datetime.now(timezone.utc).isoformat()
    result = await db.shortlists.find_one_and_update(
        {"id": shortlist_id, "owner_user_id": user["user_id"]},
        {"$pull": {"players": {"id": player_id}}, "$set": {"updated_at": now}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Shortlist not found")
    return _serialize_shortlist(result)


@api_router.post("/shortlists/{shortlist_id}/share", response_model=Shortlist)
async def share_shortlist(shortlist_id: str, request: Request, authorization: str | None = Header(default=None)):
    user = await _user_for_session(request, authorization)
    token = f"tok_{uuid.uuid4().hex}"
    result = await db.shortlists.find_one_and_update(
        {"id": shortlist_id, "owner_user_id": user["user_id"]},
        {"$set": {"share_token": token, "updated_at": datetime.now(timezone.utc).isoformat()}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Shortlist not found")
    return _serialize_shortlist(result)


@api_router.delete("/shortlists/{shortlist_id}/share", response_model=Shortlist)
async def unshare_shortlist(shortlist_id: str, request: Request, authorization: str | None = Header(default=None)):
    user = await _user_for_session(request, authorization)
    result = await db.shortlists.find_one_and_update(
        {"id": shortlist_id, "owner_user_id": user["user_id"]},
        {"$set": {"share_token": None, "updated_at": datetime.now(timezone.utc).isoformat()}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Shortlist not found")
    return _serialize_shortlist(result)


@api_router.get("/shortlists/shared/{token}", response_model=SharedShortlist)
async def get_shared_shortlist(token: str):
    doc = await db.shortlists.find_one({"share_token": token})
    if not doc:
        raise HTTPException(status_code=404, detail="Shared shortlist not found")
    serialized = _serialize_shortlist(doc)
    return {
        "id": serialized["id"],
        "owner_name": serialized.get("owner_name"),
        "name": serialized["name"],
        "notes": serialized.get("notes"),
        "tags": serialized.get("tags", []),
        "players": serialized.get("players", []),
        "updated_at": serialized["updated_at"],
    }


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[] if os.environ.get('CORS_ORIGINS') == '*' else os.environ['CORS_ORIGINS'].split(','),
    allow_origin_regex='.*' if os.environ.get('CORS_ORIGINS') == '*' else None,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
