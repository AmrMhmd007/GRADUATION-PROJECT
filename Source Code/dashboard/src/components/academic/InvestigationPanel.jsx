import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import Breadcrumb from "./Breadcrumb";
import useEscapeKey from "../../hooks/useEscapeKey";

// Stage C — Investigation & Evidence. Opened for one specific AccessEvent
// (from Command Center's recent events / anomaly indicators, an Emergency
// Override's related events, or a door's history) and shows everything the
// backend can honestly say about it: PHYSICAL FACTS (the door's current
// lock/online state), the AUTHORIZATION DECISION recorded at the time
// (never recomputed against today's data), and SECURITY INTERPRETATION
// (real anomaly indicators / overrides / audit rows that correlate with
// it) — kept visually separate so they're never mistaken for one another.
const SOURCE_LABELS = {
  access_event: "Access Event",
  anomaly: "Anomaly",
  emergency_override: "Emergency Override",
  audit_log: "Audit Log",
};

function fmt(iso) {
  if (!iso) return "—";
  return new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString();
}

export default function InvestigationPanel({ eventId, canManageStatus, onClose }) {
  useEscapeKey(onClose);
  const [detail, setDetail] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [err, setErr] = useState(null);
  const [forbidden, setForbidden] = useState(false);
  const [notFound, setNotFound] = useState(false);

  const [statusDraft, setStatusDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState(null);

  function load() {
    setErr(null);
    setForbidden(false);
    setNotFound(false);
    Promise.all([api.getAccessEventDetail(eventId), api.getAccessEventTimeline(eventId)])
      .then(([d, t]) => {
        setDetail(d);
        setTimeline(t);
        setStatusDraft(d.investigation?.status || "open");
        setNoteDraft(d.investigation?.note || "");
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setForbidden(true);
        else if (e instanceof ApiError && e.status === 404) setNotFound(true);
        else setErr(e.message);
      });
  }

  useEffect(() => {
    setDetail(null);
    setTimeline(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId]);

  async function handleSaveStatus(e) {
    e.preventDefault();
    setSaving(true);
    setSaveErr(null);
    try {
      const updated = await api.updateEventInvestigation(eventId, { status: statusDraft, note: noteDraft.trim() || null });
      setDetail((d) => ({ ...d, investigation: updated }));
    } catch (e) {
      setSaveErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  const loading = !detail && !err && !forbidden && !notFound;

  return (
    <div className="aa-modal-backdrop" onClick={onClose}>
      <div className="aa-modal" style={{ maxWidth: "780px" }} onClick={(e) => e.stopPropagation()}>
        <button type="button" className="aa-modal-close" onClick={onClose} aria-label="Close">×</button>
        <Breadcrumb crumbs={[{ label: "Investigation" }, { label: `Access Event #${eventId}` }]} />

        {forbidden && (
          <div className="form-error" style={{ marginTop: "12px" }}>
            You aren't authorized to investigate this access event — it falls outside your admin scope.
          </div>
        )}
        {notFound && <div className="form-error" style={{ marginTop: "12px" }}>Access event not found.</div>}
        {err && <div className="form-error" style={{ marginTop: "12px" }}>{err}</div>}
        {loading && <p className="muted" style={{ marginTop: "12px" }}>Loading investigation&hellip;</p>}

        {detail && (
          <>
            <section className="room-profile-section">
              <h3>Incident Summary</h3>
              <div className="aa-profile-grid" style={{ marginTop: "8px" }}>
                <div><dt>Result</dt><dd className={detail.result === "granted" ? "ok" : "bad"} style={{ fontWeight: 600 }}>{detail.result?.toUpperCase()}</dd></div>
                <div><dt>Timestamp</dt><dd>{fmt(detail.event_time)}</dd></div>
                <div><dt>Door</dt><dd>{detail.door_name || `Door #${detail.door_id}`} {detail.door_code ? `(${detail.door_code})` : ""}</dd></div>
                <div><dt>Building</dt><dd>{detail.building || "Not recorded"}</dd></div>
                <div><dt>User</dt><dd>{detail.user_name || (detail.user_id ? `User #${detail.user_id}` : "Unresolved credential")}</dd></div>
                <div><dt>Access method</dt><dd>{detail.method}</dd></div>
              </div>
              {detail.investigation && (
                <p className="muted" style={{ marginTop: "8px", fontSize: "12px" }}>
                  Investigation status: <strong>{detail.investigation.status.replace("_", " ")}</strong>
                  {detail.investigation.updated_by_name && ` — last updated by ${detail.investigation.updated_by_name}`}
                </p>
              )}
            </section>

            {canManageStatus && (
              <section className="room-profile-section">
                <h3>Investigation Status</h3>
                <form onSubmit={handleSaveStatus} style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  <select value={statusDraft} onChange={(e) => setStatusDraft(e.target.value)}>
                    <option value="open">Open</option>
                    <option value="under_review">Under Review</option>
                    <option value="resolved">Resolved</option>
                  </select>
                  <textarea
                    placeholder="Investigation note (optional)"
                    value={noteDraft}
                    onChange={(e) => setNoteDraft(e.target.value)}
                    rows={2}
                  />
                  {saveErr && <div className="form-error">{saveErr}</div>}
                  <button type="submit" disabled={saving} style={{ alignSelf: "flex-start" }}>
                    {saving ? "Saving…" : "Save status"}
                  </button>
                </form>
              </section>
            )}

            <section className="room-profile-section">
              <h3>Timeline</h3>
              {timeline === null ? (
                <p className="muted">Loading&hellip;</p>
              ) : timeline.length === 0 ? (
                <p className="muted">No correlated records in the surrounding window.</p>
              ) : (
                <ul className="aa-access-window-list">
                  {timeline.map((item, i) => (
                    <li key={i} className="aa-access-window-row" style={item.is_focus_event ? { borderColor: "var(--accent, #2563EB)" } : undefined}>
                      <div>
                        <span className="aa-status-pill pending" style={{ marginRight: "8px", fontSize: "10px" }}>
                          {SOURCE_LABELS[item.source] || item.source}
                        </span>
                        {item.description}
                      </div>
                      <span className="muted" style={{ fontSize: "11px" }}>{fmt(item.timestamp)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="room-profile-section">
              <h3>Physical State <span className="muted" style={{ fontWeight: 400, fontSize: "12px" }}>(current, not historical)</span></h3>
              {detail.physical_door_state.available ? (
                <p>
                  Door is currently <strong>{detail.physical_door_state.online ? (detail.physical_door_state.locked ? "locked" : "unlocked") : "offline"}</strong>.
                  This reflects right now, not the state at the moment of this event — no historical physical-state snapshot exists in this system.
                </p>
              ) : (
                <p className="muted">Door record unavailable.</p>
              )}
            </section>

            <section className="room-profile-section">
              <h3>Authorization Decision <span className="muted" style={{ fontWeight: 400, fontSize: "12px" }}>(recorded at the time)</span></h3>
              {!detail.evidence_available ? (
                <p className="muted">Not recorded — this event has no stored evidence snapshot. Nothing has been guessed or recomputed to fill this in.</p>
              ) : (
                <>
                  <p>
                    <span className={`aa-status-pill ${detail.authorization.authorized ? "active" : "expired"}`}>
                      {detail.authorization.authorized === true ? "AUTHORIZED" : detail.authorization.authorized === false ? "NOT AUTHORIZED" : "N/A (admin action)"}
                    </span>
                    <span style={{ marginLeft: "8px" }}>{detail.authorization.reason}</span>
                  </p>
                  <div className="aa-profile-grid" style={{ marginTop: "8px" }}>
                    <div><dt>Authorization source</dt><dd>{detail.authorization.authorization_source || "Not recorded"}</dd></div>
                    <div><dt>Permanent assignment</dt><dd>{detail.authorization.has_permanent_access === null ? "Not applicable" : detail.authorization.has_permanent_access ? "Yes" : "No"}</dd></div>
                    <div><dt>Matched access window</dt><dd>{detail.authorization.matched_window ? (detail.authorization.matched_window.recurring ? "Recurring window" : "Temporary window") : "None"}</dd></div>
                  </div>
                </>
              )}
              {detail.related_override && (
                <p className="muted" style={{ marginTop: "8px", fontSize: "12px" }}>
                  An emergency override (#{detail.related_override.override_id}, {detail.related_override.action}, "{detail.related_override.reason}")
                  was in force on this door at the time of this event.
                </p>
              )}
            </section>

            <section className="room-profile-section">
              <h3>Related Anomaly Indicators</h3>
              {detail.related_anomalies.length === 0 ? (
                <p className="muted">No related record.</p>
              ) : (
                <ul className="aa-access-window-list">
                  {detail.related_anomalies.map((a, i) => (
                    <li key={i} className="aa-access-window-row">
                      <div>
                        <span className="aa-status-pill expired" style={{ marginRight: "8px", fontSize: "10px" }}>{a.severity.replace(/_/g, " ")}</span>
                        {a.explanation}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="room-profile-section">
              <h3>Related Audit Activity</h3>
              {!detail.related_audit_available ? (
                <p className="muted">{detail.related_audit_unavailable_reason}</p>
              ) : detail.related_audit.length === 0 ? (
                <p className="muted">No related record.</p>
              ) : (
                <ul className="aa-access-window-list">
                  {detail.related_audit.map((r) => (
                    <li key={r.log_id} className="aa-access-window-row">
                      <div>{r.actor_email || "System"} — {r.action}{r.description ? ` (${r.description})` : ""}</div>
                      <span className="muted" style={{ fontSize: "11px" }}>{fmt(r.timestamp)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
