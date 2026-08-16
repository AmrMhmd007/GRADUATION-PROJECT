import { useState } from "react";

const STATUS_STYLES = {
  offline: { color: "#B45309", label: "OFFLINE" },
  locked: { color: "#059669", label: "LOCKED - SECURE" },
  unlocked: { color: "#2563EB", label: "UNLOCKED" },
};

function statusOf(door) {
  if (!door.online) return STATUS_STYLES.offline;
  return door.locked ? STATUS_STYLES.locked : STATUS_STYLES.unlocked;
}

export default function DoorCard({
  door,
  onOverride,
  onViewLogs,
  canOverride,
  canRequestAccess,
  onRequestAccess,
  onSetStatus,
  onDelete,
}) {
  const [busy, setBusy] = useState(false);
  const [requested, setRequested] = useState(false);
  const status = statusOf(door);

  async function handle(action) {
    setBusy(true);
    try {
      await onOverride(door.door_id, action);
    } finally {
      setBusy(false);
    }
  }

  async function handleRequest() {
    setBusy(true);
    try {
      await onRequestAccess(door.door_id);
      setRequested(true);
      setTimeout(() => setRequested(false), 8000);
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleStatus() {
    setBusy(true);
    try {
      await onSetStatus(door.door_id, !door.online);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Delete "${door.name}" (${door.code})? This can't be undone.`)) return;
    setBusy(true);
    try {
      await onDelete(door.door_id);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="door-card">
      <h3>{door.name}</h3>
      <div className="door-meta muted">
        {door.building}{door.floor ? ` · Floor ${door.floor}` : ""}
      </div>
      <div className="door-status">
        <span className="dot" style={{ background: status.color }} />
        <span style={{ color: status.color, fontWeight: 600 }}>{status.label}</span>
      </div>
      <div className="door-actions">
        {canOverride && (
          <button
            disabled={busy}
            onClick={() => handle(door.locked ? "unlock" : "lock")}
          >
            {door.locked ? "Unlock" : "Lock"}
          </button>
        )}
        {canOverride && (
          <button className="secondary" disabled={busy} onClick={handleToggleStatus}>
            Mark {door.online ? "Offline" : "Online"}
          </button>
        )}
        {canRequestAccess && (
          <button disabled={busy || requested} onClick={handleRequest}>
            {requested ? "Requested ✓" : "Request Access"}
          </button>
        )}
        {canOverride && (
          <button className="secondary" onClick={() => onViewLogs(door.door_id)}>
            History
          </button>
        )}
        {canOverride && (
          <button className="danger" disabled={busy} onClick={handleDelete}>
            Delete
          </button>
        )}
      </div>
    </div>
  );
}
