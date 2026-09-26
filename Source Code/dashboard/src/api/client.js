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

// FastAPI's HTTPException(detail="...") comes through as a plain string, but
// its own automatic 422 validation errors come through as an array of
// {loc, msg, type} objects (one per invalid field) — shown raw, that reads
// as "[object Object]" or a wall of JSON. This turns either shape into one
// readable sentence for the form-error divs that display e.reason/e.message
// verbatim throughout the app.
function formatErrorDetail(data) {
  const raw = data && typeof data === "object" && !Array.isArray(data) ? data.detail : data;
  if (Array.isArray(raw)) {
    const parts = raw
      .map((err) => {
        if (err && typeof err === "object") {
          const field = Array.isArray(err.loc) ? err.loc[err.loc.length - 1] : err.loc;
          return field && field !== "body" ? `${field}: ${err.msg}` : err.msg;
        }
        return String(err);
      })
      .filter(Boolean);
    return parts.length ? parts.join("; ") : null;
  }
  if (typeof raw === "string" && raw.trim()) return raw;
  return null;
}

// Fallback text ONLY for the rare response that has no usable `detail` body
// at all (almost every endpoint in this app sets one — see formatErrorDetail
// above, which is tried first and wins whenever the backend did supply
// something readable). This never overrides real backend text; it only
// covers a completely empty/unparseable error body, most commonly a 5xx
// from something outside FastAPI's own error handling (a proxy, a crash
// before the app could format a response) — i.e. "Handle backend
// unavailable state" from an actually-unavailable backend, not a made-up
// generic message layered on top of real detail.
function friendlyStatusFallback(status) {
  if (status === 401) return "Your session has expired. Please sign in again.";
  if (status === 403) return "You don't have permission to do that.";
  if (status === 404) return "That item couldn't be found — it may have been removed.";
  if (status === 409) return "That conflicts with existing data and couldn't be completed.";
  if (status === 422) return "Some of the information provided isn't valid.";
  if (status >= 500) return "The server ran into a problem. Please try again in a moment.";
  return `Request failed (${status})`;
}

// A fetch() that never reaches the server (offline, DNS failure, backend
// down, CORS) rejects with a raw TypeError like "Failed to fetch" — accurate
// but meaningless to a non-technical user. Both request() and
// uploadRequest() route through this so that failure gets the same clear,
// consistent message as any other ApiError.
async function safeFetch(url, options) {
  try {
    return await fetch(url, options);
  } catch {
    throw new ApiError(0, "Couldn't reach the server. Check your connection and try again.");
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
  const resp = await safeFetch(`${BASE_URL}${path}`, {
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
    const detail = formatErrorDetail(data) || friendlyStatusFallback(resp.status);
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

  const resp = await safeFetch(`${BASE_URL}${path}`, { method: "POST", headers, body: form });

  if (resp.status === 401) {
    unauthorizedHandler?.();
  }

  const text = await resp.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!resp.ok) {
    const detail = formatErrorDetail(data) || friendlyStatusFallback(resp.status);
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

  listAuditLogs: (params = {}) => {
    const qs = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") qs.set(key, value);
    }
    const s = qs.toString();
    return request(`/api/audit-logs${s ? `?${s}` : ""}`);
  },

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
  // Stage B — the reverse direction of the above: who has permanent access
  // TO this door, rather than which doors a given staff member has.
  listAssignmentsForDoor: (doorId) => request(`/api/doors/${doorId}/assignments`),
  addDoorAssignment: (userId, doorId) =>
    request(`/api/users/${userId}/doors`, { method: "POST", body: { door_id: doorId } }),
  removeDoorAssignment: (userId, assignmentId) =>
    request(`/api/users/${userId}/doors/${assignmentId}`, { method: "DELETE" }),

  listAlerts: (resolved) =>
    request(`/api/alerts${resolved === undefined ? "" : `?resolved=${resolved}`}`),
  resolveAlert: (alertId) => request(`/api/alerts/${alertId}/resolve`, { method: "PUT" }),

  // Energy / occupancy / checkout (see app/services/energy_service.py) —
  // setOccupancy is an admin-only manual/testing stand-in for the real path,
  // which is a room's occupancy sensor reporting straight in over MQTT.
  setOccupancy: (doorId, occupied) =>
    request(`/api/doors/${doorId}/occupancy`, { method: "POST", body: { occupied } }),
  doorPower: (doorId, limit) =>
    request(`/api/doors/${doorId}/power${limit ? `?limit=${limit}` : ""}`),
  getSystemSettings: () => request("/api/system/settings"),
  updateSystemSettings: (checkoutTime) =>
    request("/api/system/settings", { method: "PUT", body: { checkout_time: checkoutTime } }),
  runCheckoutSweep: () => request("/api/system/run-checkout-sweep", { method: "POST" }),

  listSchedules: () => request("/api/schedules"),
  createSchedule: (schedule) => request("/api/schedules", { method: "POST", body: schedule }),
  updateSchedule: (scheduleId, fields) =>
    request(`/api/schedules/${scheduleId}`, { method: "PUT", body: fields }),
  listCredentials: () => request("/api/credentials"),

  listFaculties: () => request("/api/faculties"),
  getFaculty: (facultyId) => request(`/api/faculties/${facultyId}`),
  // Accepts either a bare name string (legacy call sites) or a fields object
  // ({ name, code, description }) — Phase 5 added code/description/status to
  // the backend, so both create/update now take the full shape.
  createFaculty: (fields) =>
    request("/api/faculties", { method: "POST", body: typeof fields === "string" ? { name: fields } : fields }),
  updateFaculty: (facultyId, fields) =>
    request(`/api/faculties/${facultyId}`, {
      method: "PUT", body: typeof fields === "string" ? { name: fields } : fields,
    }),
  deleteFaculty: (facultyId) => request(`/api/faculties/${facultyId}`, { method: "DELETE" }),
  getFacultyDeletionImpact: (facultyId) => request(`/api/faculties/${facultyId}/deletion-impact`),
  cascadeDeleteFaculty: (facultyId, confirmName, password) =>
    request(`/api/faculties/${facultyId}/cascade-delete`, {
      method: "POST",
      body: { confirm_name: confirmName, password },
    }),

  // Organizational hierarchy: College(Faculty) -> Department -> Staff -> Course
  listDepartments: (facultyId) => request(`/api/departments${facultyId ? `?faculty_id=${facultyId}` : ""}`),
  getDepartment: (departmentId) => request(`/api/departments/${departmentId}`),
  createDepartment: (facultyId, fields) =>
    request("/api/departments", {
      method: "POST",
      body: { faculty_id: facultyId, ...(typeof fields === "string" ? { name: fields } : fields) },
    }),
  updateDepartment: (departmentId, fields) =>
    request(`/api/departments/${departmentId}`, { method: "PUT", body: fields }),
  deleteDepartment: (departmentId) => request(`/api/departments/${departmentId}`, { method: "DELETE" }),

  // Accepts either a bare departmentId (legacy call sites, e.g. the
  // per-department Courses tab) or a { facultyId, departmentId } filter
  // object for the global Courses Management view — the backend
  // (GET /api/courses) already supports both params and applies the
  // acting admin's scope automatically when neither is given.
  listCourses: (filter) => {
    if (filter && typeof filter === "object") {
      const params = new URLSearchParams();
      if (filter.departmentId) params.set("department_id", filter.departmentId);
      else if (filter.facultyId) params.set("faculty_id", filter.facultyId);
      const qs = params.toString();
      return request(`/api/courses${qs ? `?${qs}` : ""}`);
    }
    return request(`/api/courses${filter ? `?department_id=${filter}` : ""}`);
  },
  createCourse: (departmentId, fields) =>
    request("/api/courses", { method: "POST", body: { department_id: departmentId, ...fields } }),
  updateCourse: (courseId, fields) =>
    request(`/api/courses/${courseId}`, { method: "PUT", body: fields }),
  deleteCourse: (courseId) => request(`/api/courses/${courseId}`, { method: "DELETE" }),

  listCourseAssignments: (courseId) => request(`/api/courses/${courseId}/assignments`),
  assignStaffToCourse: (courseId, fields) =>
    request(`/api/courses/${courseId}/assignments`, {
      method: "POST", body: typeof fields === "number" ? { user_id: fields } : fields,
    }),
  updateCourseAssignment: (courseId, assignmentId, fields) =>
    request(`/api/courses/${courseId}/assignments/${assignmentId}`, { method: "PUT", body: fields }),
  removeCourseAssignment: (courseId, assignmentId) =>
    request(`/api/courses/${courseId}/assignments/${assignmentId}`, { method: "DELETE" }),

  updateStaffProfile: (userId, fields) =>
    request(`/api/users/${userId}/staff-profile`, { method: "PUT", body: fields }),

  // Scope-aware staff listing (Doctors/TAs organized by College/Department)
  listStaff: ({ facultyId, departmentId, role } = {}) => {
    const params = new URLSearchParams();
    if (facultyId) params.set("faculty_id", facultyId);
    if (departmentId) params.set("department_id", departmentId);
    if (role) params.set("role", role);
    const qs = params.toString();
    return request(`/api/staff${qs ? `?${qs}` : ""}`);
  },
  updateStaffScope: (userId, fields) => request(`/api/users/${userId}/scope`, { method: "PUT", body: fields }),
  // Clears a Doctor/TA's college+department back to "no academic
  // assignment" (distinct from updateStaffScope above, which only ever
  // assigns/reassigns to a specific one) and distinct from deleteUser
  // (which removes the account entirely) — see backend/app/routers/users.py.
  unassignStaff: (userId) => request(`/api/users/${userId}/unassign`, { method: "POST" }),

  listOperationalScopes: () => request("/api/operational-scopes"),
  createOperationalScope: (scope) => request("/api/operational-scopes", { method: "POST", body: scope }),
  deleteOperationalScope: (scopeId) => request(`/api/operational-scopes/${scopeId}`, { method: "DELETE" }),

  listAdminScopes: (userId) => request(`/api/admin-scopes${userId ? `?user_id=${userId}` : ""}`),
  createAdminScope: (grant) => request("/api/admin-scopes", { method: "POST", body: grant }),
  deleteAdminScope: (scopeId) => request(`/api/admin-scopes/${scopeId}`, { method: "DELETE" }),

  // Feature #5: Schedule-derived access authorization
  listAccessWindows: ({ userId, doorId } = {}) => {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    if (doorId) params.set("door_id", doorId);
    const qs = params.toString();
    return request(`/api/access-windows${qs ? `?${qs}` : ""}`);
  },
  createAccessWindow: (window) => request("/api/access-windows", { method: "POST", body: window }),
  updateAccessWindow: (id, fields) => request(`/api/access-windows/${id}`, { method: "PUT", body: fields }),
  deleteAccessWindow: (id) => request(`/api/access-windows/${id}`, { method: "DELETE" }),
  checkDoorAuthorization: (doorId, userId) =>
    request(`/api/doors/${doorId}/authorization${userId ? `?user_id=${userId}` : ""}`),

  // Feature #7: access anomaly indicators
  getStaffAnomalies: (userId, sinceDays) =>
    request(`/api/staff/${userId}/anomalies${sinceDays ? `?since_days=${sinceDays}` : ""}`),
  getDoorAnomalies: (doorId, sinceDays) =>
    request(`/api/doors/${doorId}/anomalies${sinceDays ? `?since_days=${sinceDays}` : ""}`),

  // Feature #8: emergency access / override
  getActiveEmergencyOverride: (doorId) => request(`/api/doors/${doorId}/emergency-override`),
  createEmergencyOverride: (doorId, payload) =>
    request(`/api/doors/${doorId}/emergency-override`, { method: "POST", body: { door_id: doorId, ...payload } }),
  revokeEmergencyOverride: (overrideId, note) =>
    request(`/api/emergency-overrides/${overrideId}/revoke`, { method: "POST", body: { note: note || null } }),
  listEmergencyOverrides: (doorId) =>
    request(`/api/emergency-overrides${doorId ? `?door_id=${doorId}` : ""}`),

  // Phase 6: Command Center summary (real, aggregated backend data only)
  getCommandCenterSummary: () => request("/api/command-center/summary"),

  // Global Search (see routers/search.py) — one authorized endpoint, real
  // data only, same RBAC/scope rules every underlying entity already has.
  globalSearch: (q, limit) => {
    const params = new URLSearchParams({ q });
    if (limit) params.set("limit", String(limit));
    return request(`/api/search?${params.toString()}`);
  },

  // Stage C: Investigation & Evidence (see routers/investigations.py)
  listAccessEvents: (params = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") q.set(k, v); });
    const qs = q.toString();
    return request(`/api/access-events${qs ? `?${qs}` : ""}`);
  },
  getAccessEventDetail: (eventId) => request(`/api/access-events/${eventId}`),
  getAccessEventTimeline: (eventId) => request(`/api/access-events/${eventId}/timeline`),
  updateEventInvestigation: (eventId, fields) =>
    request(`/api/access-events/${eventId}/investigation`, { method: "PUT", body: fields }),
  getRelatedEventsForOverride: (overrideId) => request(`/api/emergency-overrides/${overrideId}/related-events`),

  listBuildings: () => request("/api/buildings"),
  createBuilding: (name) => request("/api/buildings", { method: "POST", body: { name } }),
  deleteBuilding: (buildingId) => request(`/api/buildings/${buildingId}`, { method: "DELETE" }),

  // Smart Building: Zones / Sensors / Devices / Automation
  // (see backend app/routers/zones.py + app/services/automation_engine.py)
  listZones: () => request("/api/zones"),
  getZone: (zoneId) => request(`/api/zones/${zoneId}`),
  createZone: (zone) => request("/api/zones", { method: "POST", body: zone }),
  updateZone: (zoneId, fields) => request(`/api/zones/${zoneId}`, { method: "PUT", body: fields }),
  deleteZone: (zoneId) => request(`/api/zones/${zoneId}`, { method: "DELETE" }),

  listSensors: (zoneId) => request(`/api/sensors${zoneId ? `?zone_id=${zoneId}` : ""}`),
  listZoneSensors: (zoneId) => request(`/api/zones/${zoneId}/sensors`),
  createSensor: (zoneId, sensorType) =>
    request(`/api/zones/${zoneId}/sensors`, { method: "POST", body: { sensor_type: sensorType } }),
  reportSensorReading: (sensorId, occupied, reading) =>
    request(`/api/sensors/${sensorId}/reading`, { method: "POST", body: { occupied, reading } }),
  deleteSensor: (sensorId) => request(`/api/sensors/${sensorId}`, { method: "DELETE" }),

  listZoneDevices: (zoneId) => request(`/api/zones/${zoneId}/devices`),
  createDevice: (zoneId, device) => request(`/api/zones/${zoneId}/devices`, { method: "POST", body: device }),
  updateDevice: (deviceId, fields) => request(`/api/devices/${deviceId}`, { method: "PUT", body: fields }),
  setDeviceStatus: (deviceId, status) =>
    request(`/api/devices/${deviceId}/status`, { method: "POST", body: { status } }),
  deleteDevice: (deviceId) => request(`/api/devices/${deviceId}`, { method: "DELETE" }),

  listZoneSchedules: (zoneId) => request(`/api/zone-schedules${zoneId ? `?zone_id=${zoneId}` : ""}`),
  createZoneSchedule: (schedule) => request("/api/zone-schedules", { method: "POST", body: schedule }),
  updateZoneSchedule: (scheduleId, fields) =>
    request(`/api/zone-schedules/${scheduleId}`, { method: "PUT", body: fields }),
  deleteZoneSchedule: (scheduleId) => request(`/api/zone-schedules/${scheduleId}`, { method: "DELETE" }),

  listAutomationLogs: (zoneId, limit) =>
    request(`/api/automation/logs?${zoneId ? `zone_id=${zoneId}&` : ""}limit=${limit || 100}`),
  runAutomationOnce: () => request("/api/automation/run-once", { method: "POST" }),
  getAutomationSummary: () => request("/api/automation/summary"),
  getAutomationLogRelated: (logId) => request(`/api/automation/logs/${logId}/related`),

  // Stage D: Automation Rules CRUD (backend already had these endpoints —
  // there was previously no UI for them at all, only the read-only log feed).
  listAutomationRules: (zoneId) => request(`/api/automation/rules${zoneId ? `?zone_id=${zoneId}` : ""}`),
  createAutomationRule: (rule) => request("/api/automation/rules", { method: "POST", body: rule }),
  updateAutomationRule: (ruleId, fields) => request(`/api/automation/rules/${ruleId}`, { method: "PUT", body: fields }),
  deleteAutomationRule: (ruleId) => request(`/api/automation/rules/${ruleId}`, { method: "DELETE" }),

  listHardwareHealth: (zoneId) => request(`/api/hardware-health${zoneId ? `?zone_id=${zoneId}` : ""}`),

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
