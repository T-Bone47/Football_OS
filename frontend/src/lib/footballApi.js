import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/v1`;

const request = (path, params) => axios.get(`${API}${path}`, { params, withCredentials: true }).then(({ data }) => data);

export const getPlayers = (params = {}) => request("/players", { limit: 100, ...params });
export const getClubs = () => request("/clubs");
export const getPlayer = (playerId) => request(`/players/${playerId}`);
export const getPlayerRole = (playerId) => request(`/players/${playerId}/role`);
export const getPlayerRoleProfile = (playerId) => request(`/players/${playerId}/role-profile`);
export const getPlayerFeatures = (playerId) => request(`/players/${playerId}/features`);
export const getSimilarPlayers = (playerId, params = {}) => request(`/players/${playerId}/similar`, { limit: 10, ...params });
export const comparePlayers = (playerId, otherId) => request(`/players/${playerId}/similarity/${otherId}`);

export const apiErrorMessage = (error) => {
  if (error?.response?.status === 404) return "This capability is not available in the connected backend.";
  if (error?.response?.data?.detail) return error.response.data.detail;
  return "The connected football data service could not be reached.";
};