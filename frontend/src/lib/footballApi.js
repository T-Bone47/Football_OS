import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/v1`;

const request = (path, params) =>
  axios.get(`${API}${path}`, { params, withCredentials: true }).then(({ data }) => data);

// Canonical Football Intelligence OS endpoints (per /api/v1 contract from Football_OS repo)
export const getCompetitions = () => request("/competitions");
export const getClubs = () => request("/clubs");
export const getClub = (clubId) => request(`/clubs/${clubId}`);
export const getPlayers = (params = {}) => request("/players", { limit: 100, ...params });
export const getPlayer = (playerId) => request(`/players/${playerId}`);
export const getPlayerRole = (playerId) => request(`/players/${playerId}/role`);
export const getPlayerRoleProfile = (playerId) => request(`/players/${playerId}/role-profile`);
export const getPlayerFeatures = (playerId) => request(`/players/${playerId}/features`);
export const getPlayerMatches = (playerId) => request(`/players/${playerId}/matches`);
export const getSimilarPlayers = (playerId, params = {}) =>
  request(`/players/${playerId}/similar`, { limit: 10, ...params });
export const comparePlayers = (playerId, otherId) =>
  request(`/players/${playerId}/similarity/${otherId}`);
export const getFeatureRegistry = () => request("/features/registry");
export const getMatches = (params = {}) => request("/matches", params);
export const getMatch = (matchId) => request(`/matches/${matchId}`);
export const getMatchEvents = (matchId) => request(`/matches/${matchId}/events`);
export const getMatchLineups = (matchId) => request(`/matches/${matchId}/lineups`);
export const getMatchStatistics = (matchId) => request(`/matches/${matchId}/statistics`);
export const getMatchPlayerStats = (matchId) => request(`/matches/${matchId}/player-stats`);
export const getMatchFeatures = (matchId) => request(`/matches/${matchId}/features`);

// Backend capabilities the platform DOES NOT yet expose. UI must render "backend dependency" states rather than fabricate.
export const BACKEND_GAPS = {
  valuation: "Valuation endpoint not exposed by the connected Football Intelligence OS build.",
  tacticalFit: "Team-system tactical fit endpoint is not yet exposed by the backend.",
  transferRisk: "Transfer-risk classification endpoint is not yet exposed by the backend.",
  marketOpportunities: "Market opportunity / hidden gem endpoint is not yet exposed.",
  replacements: "Replacement finder endpoint is not yet exposed.",
  squadBuilder: "Squad construction endpoints are not yet exposed.",
  scenario: "Scenario simulator endpoint is not yet exposed.",
  matchPrediction: "Match prediction endpoint is not yet exposed by the backend.",
  research: "Research lab endpoints (models, experiments) are not yet exposed.",
  dataQuality: "Data quality summary endpoint is not yet exposed.",
};

export const apiErrorMessage = (error) => {
  if (error?.response?.status === 404) return "This capability is not available in the connected backend.";
  if (error?.response?.status === 401) return "Session expired — please sign in again.";
  if (error?.code === "ERR_NETWORK") return "The connected football data service could not be reached.";
  if (error?.response?.data?.detail) return error.response.data.detail;
  return "The connected football data service could not be reached.";
};

export const isBackendUnreachable = (error) =>
  error?.code === "ERR_NETWORK" || (error?.response?.status && error.response.status >= 500);
