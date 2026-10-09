import { useEffect, useState } from "react";
import { api } from "../../api/client";
import useEscapeKey from "../../hooks/useEscapeKey";
import { HealthPill, SourceBadge } from "./Badges";
import { fmtDateTime } from "./util";

// Room detail built from real read-models: health (derived), occupancy,
// door, devices, open faults and a unified timeline. "Open Room Profile"
// hands off to the existing Room Profile (lock/AC/light/plugs/history).
export default function RoomIntelPanel({ room, onClose, onOpenRoomProfile }) {
  const [profile, setProfile] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [err, setErr] = useState(null);
  useEscapeKey(onClose);

  useEffect(() => {
    let live = true;
    Promise.all([api.roomProfileIntel(room.zone_id), api.roomTimeline(room.zone_id, 24)])
      .then(([p, t]) => { if (live) { setProfile(p); setTimeline(t); } })
      .catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [room.zone_id]);

  const occ = profile?.occupancy;
  return (
    <div className="room-profile-overlay" onClick={onClose}>
      <div className="room-profile-card" role="dialog" aria-modal="true" aria-labelledby="ri-title" onClick={(e) => e.stopPropagation()}>
        <div className="room-profile-header">
          <h2 id="ri-title">{room.name}</h2>
          <div className="ph-actions">
            {room.door_id != null && (
              <button type="button" className="secondary" onClick={() => onOpenRoomProfile(room.door_id)}>Open Room Profile</button>
            )}
            <button type="button" className="secondary" onClick={onClose}>Close</button>
          </div>
        </div>
        {err && <div className="form-error">{err}</div>}
        {!profile && !err && <p className="muted">Loading…</p>}
        {profile && (
          <>
            <div className="ph-kv">
              <div><span>Health</span><HealthPill state={profile.health.state} /></div>
              <div><span>Occupancy</span>
                {occ.state === "UNAVAILABLE" ? <em>Unavailable</em> : <strong>{occ.count}{occ.capacity != null ? ` / ${occ.capacity}` : ""}</strong>}
              </div>
              <div><span>Counting sensor</span><HealthPill state={profile.sensor_health} /></div>
              <div><span>Door</span>
                {profile.door ? `${profile.door.online ? "online" : "offline"}, ${profile.door.locked ? "locked" : "unlocked"}` : <em>No door linked</em>}
              </div>
            </div>
            {profile.health.reasons.length > 0 && (
              <ul className="ph-small">{profile.health.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            )}
            <h3 className="ph-section-title">Central HVAC</h3>
            {!profile.hvac ? <p className="muted">No HVAC vent is configured for this room.</p> : (
              <div className="ph-small">
                <p>
                  {profile.hvac.system} → {profile.hvac.main_duct || "main duct —"} → {profile.hvac.branch_duct || "branch —"} → {profile.hvac.vent || "ceiling vent"}
                  {" "}· blower node {profile.hvac.system_node_status}
                </p>
                {profile.hvac.state === "OK" ? (
                  <p>
                    Temperature {profile.hvac.temperature_c ?? "—"} °C · Airflow {profile.hvac.airflow_m3h ?? "—"} m³/h
                    · Fan {profile.hvac.fan_running == null ? "not reported" : profile.hvac.fan_running ? "running" : "stopped"}{" "}
                    <SourceBadge source={profile.hvac.source} />
                  </p>
                ) : <p><em>Conditions unavailable</em> — {profile.hvac.reason}</p>}
              </div>
            )}
            <h3 className="ph-section-title">Devices</h3>
            {profile.devices.length === 0 ? <p className="muted">No devices registered.</p> : (
              <ul className="ph-small">
                {profile.devices.map((d) => <li key={d.device_id}>{d.name} ({d.type}) — recorded state {d.status ? "ON" : "OFF"}</li>)}
              </ul>
            )}
            <h3 className="ph-section-title">Active alerts</h3>
            {profile.open_faults.length === 0 ? <p className="muted">None.</p> : (
              <ul className="ph-small">{profile.open_faults.map((f) => <li key={f.fault_id}>{f.severity}: {f.reason}</li>)}</ul>
            )}
            <h3 className="ph-section-title">Timeline (24 h)</h3>
            {timeline.length === 0 ? <p className="muted">No recorded events in this period.</p> : (
              <div className="ph-table-wrap">
                <table>
                  <thead><tr><th>Time</th><th>Type</th><th>Event</th><th>Source</th></tr></thead>
                  <tbody>
                    {timeline.map((t, i) => (
                      <tr key={`${t.provenance.table}-${t.provenance.ref_id}-${i}`}>
                        <td>{fmtDateTime(t.timestamp)}</td>
                        <td>{t.type.replace("_", " ")}</td>
                        <td>{t.title}{t.detail ? <div className="ph-small muted">{t.detail}</div> : null}</td>
                        <td>{t.provenance.data_source ? <SourceBadge source={t.provenance.data_source} /> : <span className="muted ph-small">{t.provenance.table}</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
