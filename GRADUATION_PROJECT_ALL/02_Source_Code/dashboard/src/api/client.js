// Thin fetch wrapper around the Phase 3 backend's REST API.
// Matches the endpoint spec in Section 5 of the System Design Document.

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const TOKEN_KEY = "access_control_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `Request failed (${status})`);
    this.status = status;
  }
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const resp = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (resp.status === 204) return null;

  let data = null;
  const text = await resp.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }

  if (!resp.ok) {
    const detail = (data && data.detail) || resp.statusText;
    throw new ApiError(resp.status, detail);
  }
  return data;
}

export const api = {
  login: (email, password) =>
    request("/api/auth/login", { method: "POST", body: { email, password }, auth: false }),

  listDoors: () => request("/api/doors"),
  createDoor: (door) => request("/api/doors", { method: "POST", body: door }),
  getDoor: (doorId) => request(`/api/doors/${doorId}`),
  doorLogs: (doorId) => request(`/api/doors/${doorId}/logs`),
  overrideDoor: (doorId, action) =>
    request(`/api/doors/${doorId}/override`, { method: "POST", body: { action } }),

  listAlerts: (resolved) =>
    request(`/api/alerts${resolved === undefined ? "" : `?resolved=${resolved}`}`),
  resolveAlert: (alertId) => request(`/api/alerts/${alertId}/resolve`, { method: "PUT" }),

  listSchedules: () => request("/api/schedules"),
  listCredentials: () => request("/api/credentials"),
};

export { ApiError };
