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

export default function DoorCard({ door, onOverride, onViewLogs, canOverride }) {
  const [busy, setBusy] = useState(false);
  const status = statusOf(door);

  async function handle(action) {
    setBusy(true);
    try {
      await onOverride(door.door_id, action);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="door-card">
      <h3>{door.name}</h3>
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
        <button className="secondary" onClick={() => onViewLogs(door.door_id)}>
          History
        </button>
      </div>
    </div>
  );
}
