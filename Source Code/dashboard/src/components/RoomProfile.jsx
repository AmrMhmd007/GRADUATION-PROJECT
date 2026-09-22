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

// The single "choose a room, see everything about it" view: door lock, AC,
// light, every plug, and its access history — all in one place instead of
// scattered across the card grid and a separate history panel.
export default function RoomProfile({
  door,
  logs,
  onClose,
  canOverride,
  canRequestAccess,
  onOverride,
  onRequestAccess,
  canControlRoom,
  onToggleAc,
  onToggleLight,
  onTogglePlug,
  onAddPlug,
  onDeletePlug,
}) {
  const [busy, setBusy] = useState(false);
  const [requested, setRequested] = useState(false);
  const [newPlugLabel, setNewPlugLabel] = useState("");
  const status = statusOf(door);

  async function run(fn) {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  }

  async function handleRequest() {
    await run(async () => {
      await onRequestAccess(door.door_id);
      setRequested(true);
      setTimeout(() => setRequested(false), 8000);
    });
  }

  async function handleAddPlug() {
    const label = newPlugLabel.trim();
    if (!label) return;
    await run(async () => {
      await onAddPlug(door.door_id, label);
      setNewPlugLabel("");
    });
  }

  return (
    <div className="room-profile-overlay" onClick={onClose}>
      <div className="room-profile-card" onClick={(e) => e.stopPropagation()}>
        <div className="room-profile-header">
          <div>
            <h2>{door.name}</h2>
            <div className="muted">
              {door.building}{door.floor ? ` · Floor ${door.floor}` : ""} · {door.code}
            </div>
          </div>
          <button className="secondary" onClick={onClose}>Close</button>
        </div>

        <div className="door-status" style={{ margin: "12px 0 18px" }}>
          <span className="dot" style={{ background: status.color }} />
          <span style={{ color: status.color, fontWeight: 600 }}>{status.label}</span>
        </div>

        <section className="room-profile-section">
          <h3>Door</h3>
          <div className="door-actions" style={{ gridTemplateColumns: "1fr 1fr" }}>
            {canOverride && (
              <button disabled={busy} onClick={() => run(() => onOverride(door.door_id, door.locked ? "unlock" : "lock"))}>
                {door.locked ? "Unlock" : "Lock"}
              </button>
            )}
            {canRequestAccess && (
              <button disabled={busy || requested} onClick={handleRequest}>
                {requested ? "Requested ✓" : "Request Access"}
              </button>
            )}
          </div>
        </section>

        {(door.ac_enabled || door.light_enabled) && (
          <section className="room-profile-section">
            <h3>Climate &amp; Lighting</h3>
            <div className="door-actions" style={{ gridTemplateColumns: "1fr 1fr" }}>
              {door.ac_enabled && (
                <button
                  className={door.ac_on ? "" : "secondary"}
                  disabled={busy || !canControlRoom}
                  onClick={() => run(() => onToggleAc(door.door_id, !door.ac_on))}
                >
                  AC {door.ac_on ? "On" : "Off"}
                </button>
              )}
              {door.light_enabled && (
                <button
                  className={door.light_on ? "" : "secondary"}
                  disabled={busy || !canControlRoom}
                  onClick={() => run(() => onToggleLight(door.door_id, !door.light_on))}
                >
                  Light {door.light_on ? "On" : "Off"}
                </button>
              )}
            </div>
          </section>
        )}

        <section className="room-profile-section">
          <h3>Plugs</h3>
          {door.plugs?.length > 0 ? (
            door.plugs.map((plug) => (
              <div key={plug.plug_id} className="room-profile-plug-row">
                <button
                  className={plug.on ? "" : "secondary"}
                  disabled={busy || !canControlRoom}
                  onClick={() => run(() => onTogglePlug(door.door_id, plug.plug_id, !plug.on))}
                >
                  {plug.label}: {plug.on ? "On" : "Off"}
                </button>
                {plug.current_amps != null && (
                  <span className="muted" style={{ fontSize: "12px" }}>{plug.current_amps}A</span>
                )}
                {onDeletePlug && (
                  <button className="danger" disabled={busy} onClick={() => run(() => onDeletePlug(door.door_id, plug.plug_id))}>
                    Remove
                  </button>
                )}
              </div>
            ))
          ) : (
            <p className="muted">No plugs configured for this room.</p>
          )}
          {onAddPlug && (
            <div style={{ display: "flex", gap: "6px", marginTop: "8px" }}>
              <input
                placeholder="New plug label"
                value={newPlugLabel}
                onChange={(e) => setNewPlugLabel(e.target.value)}
                style={{ flex: 1 }}
              />
              <button className="secondary" disabled={busy} onClick={handleAddPlug}>+ Add plug</button>
            </div>
          )}
        </section>

        {canOverride && (
          <section className="room-profile-section">
            <h3>History</h3>
            {logs.length === 0 ? (
              <p className="muted">No events yet.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Credential</th>
                    <th>Method</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((e) => (
                    <tr key={e.event_id}>
                      <td>{new Date(e.event_time).toLocaleString()}</td>
                      <td>{e.credential_id ?? "-"}</td>
                      <td>{e.method}</td>
                      <td className={e.result === "granted" ? "ok" : "bad"}>{e.result}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
