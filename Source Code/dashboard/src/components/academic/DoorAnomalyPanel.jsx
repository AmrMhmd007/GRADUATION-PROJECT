import { useEffect, useState } from "react";
import { api } from "../../api/client";

const SEVERITY_CLASS = {
  UNUSUAL: "pending",
  ANOMALOUS: "pending",
  ELEVATED_RISK_INDICATOR: "expired",
};

// Door-centric anomaly view (Feature #7) — admin-only, shown inside
// RoomProfile's History section. Every indicator here comes straight from
// app/services/anomaly_detection_service.py, derived from this door's own
// stored AccessEvent history — nothing here is mocked or randomly
// generated. Labels are deliberately non-accusatory (Unusual/Anomalous/
// Elevated Risk Indicator), never "malicious" or "suspicious person."
// Stage C — same real-event-only rule as Command Center's investigation
// links: only offer "Investigate" when the evidence itself names a real
// AccessEvent id, never a link to nowhere.
function investigableEventId(indicator) {
  const ev = indicator.evidence || {};
  if (ev.event_id != null) return ev.event_id;
  if (Array.isArray(ev.event_ids) && ev.event_ids.length > 0) return ev.event_ids[ev.event_ids.length - 1];
  return null;
}

export default function DoorAnomalyPanel({ doorId, onInvestigateEvent }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.getDoorAnomalies(doorId)
      .then((r) => { if (!cancelled) setReport(r); })
      .catch((e) => { if (!cancelled) setErr(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [doorId]);

  if (loading) return <p className="muted">Checking access anomaly indicators&hellip;</p>;
  if (err) return <div className="form-error">{err}</div>;
  if (!report) return null;

  const total = report.summary.UNUSUAL + report.summary.ANOMALOUS + report.summary.ELEVATED_RISK_INDICATOR;

  return (
    <section className="room-profile-section">
      <h3>Access Anomaly Indicators</h3>
      {total === 0 ? (
        <p className="muted">No unusual access patterns detected at this room in the last 30 days.</p>
      ) : (
        <>
          <div style={{ display: "flex", gap: "8px", marginBottom: "10px", flexWrap: "wrap" }}>
            {report.summary.ELEVATED_RISK_INDICATOR > 0 && (
              <span className="aa-status-pill expired">{report.summary.ELEVATED_RISK_INDICATOR} Elevated Risk</span>
            )}
            {report.summary.ANOMALOUS > 0 && <span className="aa-status-pill pending">{report.summary.ANOMALOUS} Anomalous</span>}
            {report.summary.UNUSUAL > 0 && <span className="aa-status-pill pending">{report.summary.UNUSUAL} Unusual</span>}
          </div>
          {report.staff.map((s) => (
            <div key={s.user_id} style={{ marginBottom: "10px" }}>
              <strong style={{ fontSize: "13px" }}>{s.user_name}</strong>
              <ul className="aa-course-list">
                {s.indicators.map((ind, i) => {
                  const key = `${s.user_id}-${i}`;
                  const eventId = investigableEventId(ind);
                  return (
                    <li key={key}>
                      <span className={`aa-status-pill ${SEVERITY_CLASS[ind.severity]}`} style={{ marginRight: "6px" }}>
                        {ind.severity.replace(/_/g, " ")}
                      </span>
                      {ind.explanation}{" "}
                      <button type="button" className="link-button" onClick={() => setExpanded(expanded === key ? null : key)}>
                        {expanded === key ? "Hide evidence" : "Show evidence"}
                      </button>
                      {eventId != null && onInvestigateEvent && (
                        <button type="button" className="link-button" onClick={() => onInvestigateEvent(eventId)}>
                          Investigate
                        </button>
                      )}
                      {expanded === key && (
                        <pre style={{ fontSize: "11px", background: "var(--page-bg)", padding: "8px", borderRadius: "6px", overflowX: "auto" }}>
                          {JSON.stringify(ind.evidence, null, 2)}
                        </pre>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </>
      )}
    </section>
  );
}
