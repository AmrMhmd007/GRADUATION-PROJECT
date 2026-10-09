// Shared helpers for the cyber-physical views. Backend timestamps are UTC
// without a trailing "Z" (same convention as smart-building/sbUtils.js).
export function parseUtc(iso) {
  if (!iso) return null;
  return new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
}

export function fmtTime(iso) {
  const d = parseUtc(iso);
  return d ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";
}

export function fmtDateTime(iso) {
  const d = parseUtc(iso);
  return d ? d.toLocaleString() : "—";
}

