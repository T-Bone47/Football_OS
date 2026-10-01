// Phase 17 operations API client. Every value shown in the operations
// consoles comes from these calls; the pages hold no sample data.
import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
const OPS = `${BACKEND_URL}/api/v1/ops`;
const TOKEN_KEY = "fios_ops_token";

// Bearer tokens live in sessionStorage only (cleared when the tab closes),
// never in localStorage, and are never logged.
export function getOpsToken() {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setOpsToken(token) {
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
    else window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the token lives only for this render */
  }
}

function headers() {
  const token = getOpsToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function opsGet(path, params) {
  const { data } = await axios.get(`${OPS}${path}`, { headers: headers(), params, timeout: 60000 });
  return data;
}

export async function opsPost(path, body, params) {
  const { data } = await axios.post(`${OPS}${path}`, body ?? {}, { headers: headers(), params, timeout: 300000 });
  return data;
}

export function describeError(err) {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 401) return "Not authenticated: the operations token is missing, invalid or revoked.";
  if (status === 403) return `Not authorized: ${typeof detail === "string" ? detail : "your role lacks this permission."}`;
  if (status === 429) return "Rate limited by the API. Retry in a minute.";
  if (status) return `HTTP ${status}: ${typeof detail === "string" ? detail : JSON.stringify(detail ?? "request failed")}`;
  return `Backend unreachable (${err?.message || "network error"}).`;
}
