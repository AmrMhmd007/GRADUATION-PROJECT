// Small shared helpers for the Smart Building dashboard components — kept
// in one place so formatting (watts, elapsed time, schedule matching) stays
// consistent across the status header, zone cards, zone detail, and the
// automation log feed instead of drifting between copy-pasted versions.

export function formatWatts(watts) {
  if (watts == null) return "—";
  if (watts >= 1000) return `${(watts / 1000).toFixed(1)} kW`;
  return `${Math.round(watts)} W`;
}

export function formatElapsedSince(isoString) {
  if (!isoString) return null;
  // Backend timestamps are UTC without a trailing "Z" — new Date() parses a
  // bare "YYYY-MM-DDTHH:mm:ss.ffffff" as *local* time, which would make
  // this drift by the browser's UTC offset. Appending "Z" fixes that.
  const iso = isoString.endsWith("Z") ? isoString : `${isoString}Z`;
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0) return "0s";
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) return `${seconds}s`;
  if (minutes < 60) return `${minutes}m ${seconds}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

// Display-only best-effort match of the backend's ZoneSchedule scoring
// (app/services/automation_engine.py's get_schedule_state) — a zone-specific
// row outranks the building-wide default, a day-specific row outranks an
// every-day one. Used only to show an approximate verification-window
// length next to a live countdown; the backend remains the sole source of
// truth for the actual automation decision.
export function pickBestSchedule(schedules, zoneId) {
  if (!schedules || schedules.length === 0) return null;
  const dow = new Date().getDay() === 0 ? 6 : new Date().getDay() - 1; // JS: 0=Sun -> backend: 0=Mon
  const applicable = schedules.filter((s) => s.day_of_week == null || s.day_of_week === dow);
  const pool = applicable.length ? applicable : schedules;
  const score = (s) => (s.zone_id === zoneId ? 2 : 0) + (s.day_of_week === dow ? 1 : 0);
  return pool.reduce((best, s) => (best == null || score(s) > score(best) ? s : best), null);
}

export const OCCUPANCY_LABELS = {
  OCCUPIED: "Occupied",
  EMPTY: "Empty",
  VERIFYING: "Verifying…",
  UNKNOWN: "Unknown",
};

export const DECISION_LABELS = {
  NO_ACTION: "No action",
  VERIFICATION_STARTED: "Verification started",
  VERIFICATION_CANCELLED: "Verification cancelled",
  SHUTDOWN_NON_CRITICAL: "Shutdown non-critical loads",
  SHUTDOWN_SKIPPED_UNCERTAIN: "Shutdown skipped — uncertain",
};

export function timeOfDay(isoString) {
  const iso = isoString.endsWith("Z") ? isoString : `${isoString}Z`;
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
