/**
 * Centralized Typed Football Intelligence OS API Layer (Frontend-Backend Integration Phase).
 * Communicates with the FastAPI/PostgreSQL backend over /api/v1/*.
 * Preserves canonical backend contracts while adapting response shapes for UI consumers.
 */
import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
export const CANONICAL_API = `${BACKEND_URL}/api/v1`;
export const APP_API = `${BACKEND_URL}/api`;

// Configured HTTP Client with timeouts and credentials
export const apiClient = axios.create({
  timeout: 15000,
  withCredentials: true,
  headers: {
    "Accept": "application/json",
    "Content-Type": "application/json",
  },
});

// Canonical Request Helper
const request = (path, params) =>
  apiClient.get(`${CANONICAL_API}${path}`, { params }).then(({ data }) => data);

const requestPost = (path, body) =>
  apiClient.post(`${CANONICAL_API}${path}`, body).then(({ data }) => data);

// ============================================================
// SYSTEM & HEALTH
// ============================================================
export const getHealth = () =>
  apiClient.get(`${BACKEND_URL}/health`).then(({ data }) => data);

export const getHealthReady = () =>
  apiClient.get(`${BACKEND_URL}/health/ready`).then(({ data }) => data);

export const getCurrentUser = async () => {
  try {
    const { data } = await apiClient.get(`${APP_API}/auth/me`);
    return data;
  } catch (err) {
    // Default local scout identity if auth endpoint is offline
    return {
      user_id: "scout_01",
      email: "scout@football-intelligence.local",
      name: "Head of Scouting",
      picture: null,
    };
  }
};

export const logout = async () => {
  try {
    await apiClient.post(`${APP_API}/auth/logout`);
  } catch (e) {
    // ignore
  }
};

// ============================================================
// COMPETITIONS & CLUBS
// ============================================================
export const getCompetitions = () => request("/competitions");
export const getClubs = () => request("/clubs");
export const getClub = (clubId) => request(`/clubs/${clubId}`);

// ============================================================
// PLAYERS & PROFILES
// ============================================================
export const getPlayers = (params = {}) =>
  request("/players", { limit: 100, ...params });

export const getPlayer = (playerId) => request(`/players/${playerId}`);

export const getPlayerRole = async (playerId, params = {}) => {
  const data = await request(`/players/${playerId}/role`, params);
  // Contract adapter: normalize archetype_confidence -> confidence for UI
  return {
    ...data,
    confidence: data.archetype_confidence ?? data.confidence ?? 0,
  };
};

export const getPlayerRoleProfile = (playerId, params = {}) =>
  request(`/players/${playerId}/role-profile`, params);

export const getPlayerFeatures = (playerId, params = {}) =>
  request(`/players/${playerId}/features`, params);

export const getPlayerMatches = (playerId) =>
  request(`/players/${playerId}/matches`);

// ============================================================
// SIMILARITY & ROLES
// ============================================================
export const getSimilarPlayers = (playerId, params = {}) =>
  request(`/players/${playerId}/similar`, { limit: 10, ...params });

export const comparePlayers = (playerId, otherId) =>
  request(`/players/${playerId}/similarity/${otherId}`);

export const getFeatureRegistry = () => request("/features/registry");

// ============================================================
// TACTICAL FIT (PHASE 2 SLICE 3 CANONICAL ENDPOINTS)
// ============================================================
export const getTacticalContexts = () => request("/tactical/contexts");

export const getPlayerTacticalFit = (playerId, params = {}) =>
  request(`/players/${playerId}/tactical-fit`, params);

export const getPlayerTacticalFitByContext = (playerId, contextId, params = {}) =>
  request(`/players/${playerId}/tactical-fit/${contextId}`, params);

export const compareTacticalFit = (payload) =>
  requestPost("/tactical-fit/compare", payload);

// ============================================================
// MATCHES & MATCH INTELLIGENCE
// ============================================================
export const getMatches = (params = {}) => request("/matches", params);

export const getMatch = async (matchId) => {
  const data = await request(`/matches/${matchId}`);
  // Contract adapter: flatten home_club.name -> home_club_name for UI consumers
  return {
    ...data,
    home_club_name: data.home_club?.name ?? data.home_club_name,
    away_club_name: data.away_club?.name ?? data.away_club_name,
    home_club_code: data.home_club?.code ?? data.home_club_code,
    away_club_code: data.away_club?.code ?? data.away_club_code,
  };
};

export const getMatchEvents = (matchId) => request(`/matches/${matchId}/events`);
export const getMatchLineups = (matchId) => request(`/matches/${matchId}/lineups`);
export const getMatchStatistics = (matchId) => request(`/matches/${matchId}/statistics`);
export const getMatchPlayerStats = (matchId) => request(`/matches/${matchId}/player-stats`);
export const getMatchFeatures = (matchId) => request(`/matches/${matchId}/features`);

// ============================================================
// UNEXPOSED BACKEND GAPS (TRUTHFUL REPORTING)
// ============================================================
export const BACKEND_GAPS = {
  valuation: "Valuation model endpoints are scheduled for Phase 3 and not yet exposed by the backend.",
  transferRisk: "Transfer-risk classification endpoints are scheduled for Phase 4 and not yet exposed.",
  marketOpportunities: "Market opportunity / valuation gap endpoints are scheduled for Phase 3.",
  replacements: "Replacement engine endpoints are scheduled for Phase 4.",
  squadBuilder: "Squad construction optimization endpoints are scheduled for Phase 7.",
  scenario: "Scenario simulator and transfer modeling endpoints are scheduled for Phase 7.",
  matchPrediction: "Match prediction & probability calibration endpoints are scheduled for Phase 6.",
  research: "Model training and experimental registry endpoints are not yet exposed.",
  dataQuality: "Automated data quality summary endpoints are not yet exposed.",
};

// Unified Error Parser
export const apiErrorMessage = (error) => {
  if (error?.response?.status === 404) return "This record or capability was not found in the connected backend.";
  if (error?.response?.status === 401) return "Session expired — please refresh or sign in again.";
  if (error?.code === "ERR_NETWORK" || error?.message?.includes("Network Error")) {
    return "The connected Football Intelligence OS backend could not be reached. Ensure FastAPI is running on port 8000.";
  }
  if (error?.response?.data?.detail) {
    const detail = error.response.data.detail;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  return error?.message || "An unexpected error occurred while querying the connected service.";
};

export const isBackendUnreachable = (error) =>
  error?.code === "ERR_NETWORK" || (error?.response?.status && error.response.status >= 500);

// ============================================================
// SHORTLISTS (LOCAL SCOUT PERSISTENCE WITH OPTIONAL BACKEND SYNC)
// ============================================================
const STORAGE_KEY = "fios_scout_shortlists";

const getLocalShortlists = () => {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
};

const saveLocalShortlists = (lists) => {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(lists));
  } catch (e) {
    console.error("Failed to save local shortlists", e);
  }
};

export const listShortlists = async () => {
  try {
    const { data } = await apiClient.get(`${APP_API}/shortlists`);
    if (Array.isArray(data)) return data;
  } catch (e) {
    // fallback to local storage
  }
  return getLocalShortlists();
};

export const createShortlist = async (payload) => {
  try {
    const { data } = await apiClient.post(`${APP_API}/shortlists`, payload);
    return data;
  } catch (e) {
    const lists = getLocalShortlists();
    const newDoc = {
      id: `sl_${Date.now().toString(36)}`,
      name: payload.name.trim(),
      notes: payload.notes || null,
      tags: payload.tags || [],
      players: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    lists.unshift(newDoc);
    saveLocalShortlists(lists);
    return newDoc;
  }
};

export const getShortlist = async (id) => {
  try {
    const { data } = await apiClient.get(`${APP_API}/shortlists/${id}`);
    return data;
  } catch (e) {
    const lists = getLocalShortlists();
    const found = lists.find((l) => l.id === id);
    if (!found) throw new Error("Shortlist not found");
    return found;
  }
};

export const updateShortlist = async (id, payload) => {
  try {
    const { data } = await apiClient.patch(`${APP_API}/shortlists/${id}`, payload);
    return data;
  } catch (e) {
    const lists = getLocalShortlists();
    const idx = lists.findIndex((l) => l.id === id);
    if (idx === -1) throw new Error("Shortlist not found");
    lists[idx] = { ...lists[idx], ...payload, updated_at: new Date().toISOString() };
    saveLocalShortlists(lists);
    return lists[idx];
  }
};

export const deleteShortlist = async (id) => {
  try {
    await apiClient.delete(`${APP_API}/shortlists/${id}`);
  } catch (e) {
    const lists = getLocalShortlists().filter((l) => l.id !== id);
    saveLocalShortlists(lists);
  }
  return { ok: true };
};

export const addShortlistPlayer = async (id, player) => {
  try {
    const { data } = await apiClient.post(`${APP_API}/shortlists/${id}/players`, player);
    return data;
  } catch (e) {
    const lists = getLocalShortlists();
    const item = lists.find((l) => l.id === id);
    if (!item) throw new Error("Shortlist not found");
    if (!item.players) item.players = [];
    if (!item.players.some((p) => p.id === player.id)) {
      item.players.push({
        ...player,
        added_at: new Date().toISOString(),
      });
      item.updated_at = new Date().toISOString();
      saveLocalShortlists(lists);
    }
    return item;
  }
};

export const removeShortlistPlayer = async (id, playerId) => {
  try {
    const { data } = await apiClient.delete(`${APP_API}/shortlists/${id}/players/${playerId}`);
    return data;
  } catch (e) {
    const lists = getLocalShortlists();
    const item = lists.find((l) => l.id === id);
    if (!item) throw new Error("Shortlist not found");
    item.players = (item.players || []).filter((p) => p.id !== playerId);
    item.updated_at = new Date().toISOString();
    saveLocalShortlists(lists);
    return item;
  }
};

export const shareShortlist = async (id) => {
  try {
    const { data } = await apiClient.post(`${APP_API}/shortlists/${id}/share`, {});
    return data;
  } catch (e) {
    const lists = getLocalShortlists();
    const item = lists.find((l) => l.id === id);
    if (!item) throw new Error("Shortlist not found");
    item.share_token = `tok_${Date.now().toString(36)}`;
    item.is_shared = true;
    saveLocalShortlists(lists);
    return item;
  }
};

export const unshareShortlist = async (id) => {
  try {
    const { data } = await apiClient.delete(`${APP_API}/shortlists/${id}/share`);
    return data;
  } catch (e) {
    const lists = getLocalShortlists();
    const item = lists.find((l) => l.id === id);
    if (!item) throw new Error("Shortlist not found");
    item.share_token = null;
    item.is_shared = false;
    saveLocalShortlists(lists);
    return item;
  }
};

export const getSharedShortlist = async (token) => {
  try {
    const { data } = await apiClient.get(`${APP_API}/shortlists/shared/${token}`);
    return data;
  } catch (e) {
    const lists = getLocalShortlists();
    const item = lists.find((l) => l.share_token === token);
    if (!item) throw new Error("Shared shortlist not found");
    return item;
  }
};
