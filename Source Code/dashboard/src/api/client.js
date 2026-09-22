// Thin fetch wrapper around the Phase 3 backend's REST API.
// Matches the endpoint spec in Section 5 of the System Design Document.

// VITE_API_BASE_URL (.env) wins if set — that's for a real deployment with a
// fixed domain (e.g. a uni server where the API isn't on the same host/port
// as the dashboard). Otherwise, default to whatever host the dashboard
// itself was loaded from, on port 8000: opened as localhost:5173 on this
// Mac, the API is localhost:8000; opened as 192.168.1.23:5173 from a TA's
// phone on the same network, the API is 192.168.1.23:8000 automatically —
// no per-device or per-network config needed to test on the LAN.
const BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  `${window.location.protocol}//${window.location.hostname}:8000`;
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

// Fires when an *authenticated* request comes back 401 — i.e. the session's
// token was rejected (expired/invalid), not just a wrong password on the
// login screen itself (that request is sent with auth:false). AuthContext
// registers itself here so an expired session logs the user out and sends
// them back to the login screen instead of the dashboard silently retrying
// the same 401'd request forever (e.g. the 5s door/alert polling).
let unauthorizedHandler = null;
export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
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

  if (resp.status === 401 && auth) {
    unauthorizedHandler?.();
  }

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

// Separate from request() because file uploads need FormData, not JSON —
// the browser sets its own multipart Content-Type (with boundary) as long
// as we don't set one ourselves.
async function uploadRequest(path, file, extraFields = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const form = new FormData();
  form.append("file", file);
  for (const [key, value] of Object.entries(extraFields)) {
    form.append(key, value);
  }

  const resp = await fetch(`${BASE_URL}${path}`, { method: "POST", headers, body: form });

  if (resp.status === 401) {
    unauthorizedHandler?.();
  }

  const text = await resp.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!resp.ok) {
    const detail = (data && data.detail) || resp.statusText;
    throw new ApiError(resp.status, detail);
  }
  return data;
}

// photo_url from the API is a relative path (e.g. "/media/avatars/x.jpg") —
// this turns it into an absolute URL the <img> tag can actually load.
export function mediaUrl(path) {
  if (!path) return null;
  return `${BASE_URL}${path}`;
}

export const api = {
  login: (email, password) =>
    request("/api/auth/login", { method: "POST", body: { email, password }, auth: false }),
  forgotPassword: (email) =>
    request("/api/auth/forgot-password", { method: "POST", body: { email }, auth: false }),
  checkPasswordResetStatus: (token) =>
    request(`/api/auth/forgot-password/status?token=${encodeURIComponent(token)}`, { auth: false }),
  resetPassword: (token, newPassword) =>
    request("/api/auth/reset-password", {
      method: "POST",
      body: { request_token: token, new_password: newPassword },
      auth: false,
    }),

  listPasswordResets: () => request("/api/password-resets"),
  approvePasswordReset: (requestId) =>
    request(`/api/password-resets/${requestId}/approve`, { method: "POST" }),
  denyPasswordReset: (requestId) =>
    request(`/api/password-resets/${requestId}/deny`, { method: "POST" }),

  listUsers: () => request("/api/users"),
  createUser: (user) => request("/api/users", { method: "POST", body: user }),
  importUsers: (file, role) => uploadRequest("/api/users/import", file, { role }),
  deleteUser: (userId) => request(`/api/users/${userId}`, { method: "DELETE" }),

  listDoors: () => request("/api/doors"),
  createDoor: (door) => request("/api/doors", { method: "POST", body: door }),
  importDoors: (file) => uploadRequest("/api/doors/import", file),
  deleteDoor: (doorId) => request(`/api/doors/${doorId}`, { method: "DELETE" }),
  getDoor: (doorId) => request(`/api/doors/${doorId}`),
  doorLogs: (doorId) => request(`/api/doors/${doorId}/logs`),
  overrideDoor: (doorId, action) =>
    request(`/api/doors/${doorId}/override`, { method: "POST", body: { action } }),
  requestDoorAccess: (doorId) => request(`/api/doors/${doorId}/request-access`, { method: "POST" }),
  setDoorStatus: (doorId, online) =>
    request(`/api/doors/${doorId}/status`, { method: "POST", body: { online } }),
  toggleAc: (doorId, on) => request(`/api/doors/${doorId}/ac`, { method: "POST", body: { on } }),
  toggleLight: (doorId, on) => request(`/api/doors/${doorId}/light`, { method: "POST", body: { on } }),
  addPlug: (doorId, label) =>
    request(`/api/doors/${doorId}/plugs`, { method: "POST", body: { label } }),
  togglePlug: (doorId, plugId, on) =>
    request(`/api/doors/${doorId}/plugs/${plugId}`, { method: "POST", body: { on } }),
  deletePlug: (doorId, plugId) =>
    request(`/api/doors/${doorId}/plugs/${plugId}`, { method: "DELETE" }),

  listDoorAssignments: (userId) => request(`/api/users/${userId}/doors`),
  addDoorAssignment: (userId, doorId) =>
    request(`/api/users/${userId}/doors`, { method: "POST", body: { door_id: doorId } }),
  removeDoorAssignment: (userId, assignmentId) =>
    request(`/api/users/${userId}/doors/${assignmentId}`, { method: "DELETE" }),

  listAlerts: (resolved) =>
    request(`/api/alerts${resolved === undefined ? "" : `?resolved=${resolved}`}`),
  resolveAlert: (alertId) => request(`/api/alerts/${alertId}/resolve`, { method: "PUT" }),

  listSchedules: () => request("/api/schedules"),
  listCredentials: () => request("/api/credentials"),

  listFaculties: () => request("/api/faculties"),
  createFaculty: (name) => request("/api/faculties", { method: "POST", body: { name } }),

  listBuildings: () => request("/api/buildings"),
  createBuilding: (name) => request("/api/buildings", { method: "POST", body: { name } }),
  deleteBuilding: (buildingId) => request(`/api/buildings/${buildingId}`, { method: "DELETE" }),

  getMe: () => request("/api/users/me"),
  updateProfile: (fields) => request("/api/users/me/profile", { method: "PATCH", body: fields }),
  changePassword: (currentPassword, newPassword) =>
    request("/api/users/me/password", {
      method: "PATCH",
      body: { current_password: currentPassword, new_password: newPassword },
    }),
  uploadPhoto: (file) => uploadRequest("/api/users/me/photo", file),
  refreshToken: () => request("/api/auth/refresh", { method: "POST" }),
};

export { ApiError };
