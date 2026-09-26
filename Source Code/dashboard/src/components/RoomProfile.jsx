import { useEffect, useState } from "react";
import { api } from "../api/client";
import useEscapeKey from "../hooks/useEscapeKey";
import DoorAnomalyPanel from "./academic/DoorAnomalyPanel";
import EmergencyOverridePanel from "./academic/EmergencyOverridePanel";
import AccessAuthorizationPanel from "./academic/AccessAuthorizationPanel";
import { OCCUPANCY_LABELS, formatWatts } from "./smart-building/sbUtils";

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
  onSetOccupancy,
  onAuthorizationChecked,
  onInvestigateEvent,
  onOpenZone,
}) {
  useEscapeKey(onClose);
  const [busy, setBusy] = useState(false);
  const [requested, setRequested] = useState(false);
  const [newPlugLabel, setNewPlugLabel] = useState("");
  const status = statusOf(door);

  // Stage E / E4: a Room (Door) and a Smart Building Zone are two different
  // models that can be linked (Zone.door_id) — until now there was no way to
  // see that link from this screen at all. This is a real, existing
  // relationship (not a guess): GET /api/zones already returns every zone
  // with its door_id, so this just finds the one (if any) pointing at this
  // door. A door with no linked zone is common (most doors aren't wired into
  // Smart Building) and is reported as such, not hidden or errored.
  const [zone, setZone] = useState(undefined); // undefined = loading, null = none found
  useEffect(() => {
    let cancelled = false;
    setZone(undefined);
    api.listZones()
      .then((zones) => {
        if (cancelled) return;
        setZone(zones.find((z) => z.door_id === door.door_id) || null);
      })
      .catch(() => { if (!cancelled) setZone(null); });
    return () => { cancelled = true; };
  }, [door.door_id]);

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

        <div className="door-status" style={{ margin: "12px 0 18px", flexWrap: "wrap", gap: "10px" }}>
          <span className="dot" style={{ background: status.color }} />
          <span style={{ color: status.color, fontWeight: 600 }}>{status.label}</span>
          {door.occupied === true && (
            <span style={{ color: "#B45309", fontWeight: 600 }}>&middot; OCCUPIED</span>
          )}
          {door.occupied === false && (
            <span style={{ color: "#059669", fontWeight: 600 }}>&middot; VACANT</span>
          )}
          {door.occupied == null && (
            <span className="muted">&middot; No occupancy sensor</span>
          )}
          {onSetOccupancy && (
            <span style={{ display: "flex", gap: "6px" }}>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => run(() => onSetOccupancy(door.door_id, true))}
                title="Testing aid until a real occupancy sensor is wired up"
              >
                Mark Occupied
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => run(() => onSetOccupancy(door.door_id, false))}
                title="Testing aid until a real occupancy sensor is wired up"
              >
                Mark Vacant
              </button>
            </span>
          )}
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

        {canOverride && (
          <section className="room-profile-section">
            <h3>Smart Building Zone</h3>
            {zone === undefined && <p className="muted">Checking for a linked Smart Building zone&hellip;</p>}
            {zone === null && (
              <p className="muted">This room isn't linked to a Smart Building zone (no automation/device data for it).</p>
            )}
            {zone && (
              <>
                <div className="door-status" style={{ margin: "6px 0" }}>
                  <span className="sb-occupancy-state" data-state={zone.occupancy_state}>
                    {OCCUPANCY_LABELS[zone.occupancy_state] || zone.occupancy_state}
                  </span>
                  <span className="muted">&middot; {(zone.devices || []).length} device{(zone.devices || []).length === 1 ? "" : "s"}</span>
                  <span className="muted">
                    &middot; {formatWatts((zone.devices || []).reduce((s, d) => s + (d.status ? d.current_power || 0 : 0), 0))}
                  </span>
                </div>
                {onOpenZone && (
                  <button type="button" className="secondary" onClick={() => onOpenZone(zone.zone_id)}>
                    Manage in Smart Building
                  </button>
                )}
              </>
            )}
          </section>
        )}

        {canOverride && (
          <AccessAuthorizationPanel doorId={door.door_id} door={door} onChecked={onAuthorizationChecked} />
        )}

        {(door.ac_enabled || door.light_enabled) && (
          <section className="room-profile-section">
            <h3>Climate &amp; Lighting</h3>
            <div className="door-actions" style={{ gridTemplateColumns: "1fr 1fr" }}>
              {door.ac_enabled && (
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <button
                    className={door.ac_on ? "" : "secondary"}
                    disabled={busy || !canControlRoom}
                    onClick={() => run(() => onToggleAc(door.door_id, !door.ac_on))}
                  >
                    AC {door.ac_on ? "On" : "Off"}
                  </button>
                  {door.ac_watts != null && (
                    <span className="muted" style={{ fontSize: "12px" }}>{door.ac_watts}W</span>
                  )}
                </div>
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
                {plug.watts != null && (
                  <span className="muted" style={{ fontSize: "12px" }}>{plug.watts}W</span>
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

        {canOverride && (
          <EmergencyOverridePanel doorId={door.door_id} currentlyLocked={door.locked} onInvestigateEvent={onInvestigateEvent} />
        )}

        {canOverride && <DoorAnomalyPanel doorId={door.door_id} onInvestigateEvent={onInvestigateEvent} />}
      </div>
    </div>
  );
}
