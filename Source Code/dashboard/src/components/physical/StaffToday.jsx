import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import FaceIdCard from "./FaceIdCard";
import { HealthPill, Sparkline, SourceBadge } from "./Badges";
import { fmtTime, parseUtc } from "./util";

function ClassCard({ c }) {
  const [hist, setHist] = useState([]);
  useEffect(() => {
    if (!c.in_progress || c.zone_id == null) return undefined;
    let live = true;
    const load = () => api.occupancyZone(c.zone_id, 3).then((r) => live && setHist(r.history)).catch(() => {});
    load();
    const id = setInterval(load, 30000);
    return () => { live = false; clearInterval(id); };
  }, [c.zone_id, c.in_progress]);

  const occ = c.occupancy;
  const unavailable = c.in_progress && (!occ || occ.state === "UNAVAILABLE");
  return (
    <article className="ph-card ph-class" data-active={c.in_progress}>
      <div className="ph-card-head">
        <h3>{c.course_code || "Class"}{c.course_name ? ` — ${c.course_name}` : ""}</h3>
        {c.in_progress && <span className="ph-pill" data-state="HEALTHY">CLASS IN PROGRESS</span>}
      </div>
      <p className="ph-small">{c.room || "Room not linked"} · {c.start}–{c.end}</p>
      {c.in_progress && (
        <>
          {unavailable ? (
            <p className="ph-count-unavailable" role="status">Occupancy unavailable{occ?.reason ? ` — ${occ.reason}` : ""}</p>
          ) : (
            <p className="ph-count" aria-live="polite">
              <strong>{occ.count}</strong>
              {occ.capacity != null && <span> / {occ.capacity}</span>} people
            </p>
          )}
          <p className="ph-small muted">
            Last updated {occ?.last_updated ? fmtTime(occ.last_updated) : "—"} · Sensor {c.sensor_health || "UNKNOWN"}
            {occ?.source && <> · <SourceBadge source={occ.source} /></>}
          </p>
          <Sparkline
            label="People count over the last 3 hours"
            points={hist.map((h) => ({ t: parseUtc(h.recorded_at).getTime(), v: h.count }))}
          />
        </>
      )}
    </article>
  );
}

function FaultRow({ f, onChange }) {
  const [busy, setBusy] = useState(false);
  async function act(action) {
    setBusy(true);
    try { await api.deviceFaultAction(f.fault_id, action); } finally { setBusy(false); onChange(); }
  }
  return (
    <li className="ph-fault" data-severity={f.severity}>
      <div>
        <strong>{f.room}</strong> — {f.device} issue
        <div className="ph-small">{f.reason}{f.reported_issue ? " · Reported" : ""}</div>
      </div>
      <div className="ph-actions">
        <button type="button" className="secondary" disabled={busy} onClick={() => act("retry-check")}>Retry Check</button>
        <button type="button" className="secondary" disabled={busy || f.reported_issue} onClick={() => act("report")}>
          {f.reported_issue ? "Reported" : "Report Issue"}
        </button>
      </div>
    </li>
  );
}

export default function StaffToday() {
  const [classes, setClasses] = useState(null);
  const [faults, setFaults] = useState([]);
  const [err, setErr] = useState(null);

  const [tick, setTick] = useState(0);
  const load = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    let live = true;
    Promise.all([api.occupancyMyClasses(), api.deviceFaults()])
      .then(([c, f]) => { if (live) { setClasses(c); setFaults(f); setErr(null); } })
      .catch((e) => { if (live) setErr(e.message); });
    return () => { live = false; };
  }, [tick]);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="ph-staff">
      {err && <div className="form-error">{err}</div>}
      {/* First-login: Face ID setup status is the first thing a new Doctor/TA sees. */}
      <FaceIdCard />
      {faults.length > 0 && (
        <section className="ph-card" aria-labelledby="ph-faults-h">
          <div className="ph-card-head"><h3 id="ph-faults-h">Room alerts</h3><HealthPill state="WARNING" /></div>
          <ul className="ph-fault-list">
            {faults.map((f) => <FaultRow key={f.fault_id} f={f} onChange={load} />)}
          </ul>
        </section>
      )}
      <h3 className="ph-section-title">Today</h3>
      {classes && classes.length === 0 && <p className="muted">No classes scheduled for you today.</p>}
      <div className="ph-grid">
        {(classes || []).map((c, i) => <ClassCard key={`${c.door_code}-${c.start}-${i}`} c={c} />)}
      </div>
    </div>
  );
}
