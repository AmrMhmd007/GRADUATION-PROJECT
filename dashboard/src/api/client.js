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
