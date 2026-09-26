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
  onOpenRoom,
}) {
  const [busy, setBusy] = useState(false);
  const [requested, setRequested] = useState(false);
  const status = statusOf(door);
  const isRoom = door.category === "access_service";

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
        {isRoom && onOpenRoom ? (
          // Rooms open a single profile with the door lock, AC, light,
          // plugs, and history together — see RoomProfile.
          <button onClick={() => onOpenRoom(door.door_id)}>View Room</button>
        ) : (
          canOverride && (
            <button
              disabled={busy}
              onClick={() => handle(door.locked ? "unlock" : "lock")}
            >
              {door.locked ? "Unlock" : "Lock"}
            </button>
          )
        )}
        {canRequestAccess && !isRoom && (
          <button disabled={busy || requested} onClick={handleRequest}>
            {requested ? "Requested ✓" : "Request Access"}
          </button>
        )}
      </div>

      {/* Secondary/routine actions converge on the same lightweight
          text-link treatment Academic Administration's cards already use
          for their equivalent actions (Edit / Deactivate / Delete — see
          CollegeGrid.jsx) rather than the heavier filled/outlined button
          chrome this card used for every action before. Delete keeps the
          same real window.confirm() prompt and backend call it already
          had (see handleDelete above) — only its visual weight changes,
          via the same .aa-danger-text color CollegeGrid's own Delete link
          already uses, so it still reads as clearly destructive next to
          the neutral links beside it. */}
      {canOverride && (
        <div className="door-actions-secondary">
          <button type="button" className="link-button" disabled={busy} onClick={handleToggleStatus}>
            Mark {door.online ? "Offline" : "Online"}
          </button>
          {!isRoom && (
            <button type="button" className="link-button" onClick={() => onViewLogs(door.door_id)}>
              History
            </button>
          )}
          {!isRoom && onOpenRoom && (
            // Main/critical doors get the same detail view a Room gets
            // (status, history, emergency override, anomaly indicators) —
            // previously only reachable by clicking through from Command
            // Center, never directly from this card.
            <button type="button" className="link-button" onClick={() => onOpenRoom(door.door_id)}>
              View Details
            </button>
          )}
          <button type="button" className="link-button aa-danger-text" disabled={busy} onClick={handleDelete}>
            Delete
          </button>
        </div>
      )}
    </div>
  );
}
