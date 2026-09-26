import { useEffect, useState } from "react";
import { api } from "../../api/client";

const SEVERITY_CLASS = {
  UNUSUAL: "pending",
  ANOMALOUS: "pending",
  ELEVATED_RISK_INDICATOR: "expired",
};

// Staff-centric anomaly view (Feature #7), shown on a Doctor/TA's profile.
// Every indicator is derived from this person's own stored AccessEvent
// history (RFID swipes + schedule_check audit rows) — never mock data, and
// never a claim of malicious intent, just an observable deviation from
// their own recorded pattern.
export default function StaffAnomalySection({ staff }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.getStaffAnomalies(staff.user_id)
      .then((r) => { if (!cancelled) setReport(r); })
      .catch((e) => { if (!cancelled) setErr(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [staff.user_id]);

  return (
    <section className="aa-profile-section">
      <h3>Access Anomaly Indicators (last 30 days)</h3>
      {loading && <p className="muted">Checking access history&hellip;</p>}
      {err && <div className="form-error">{err}</div>}
      {report && (
        report.indicators.length === 0 ? (
          <p className="muted">No unusual access patterns detected.</p>
        ) : (
          <>
            <div style={{ display: "flex", gap: "8px", marginBottom: "8px", flexWrap: "wrap" }}>
              {report.summary.ELEVATED_RISK_INDICATOR > 0 && (
                <span className="aa-status-pill expired">{report.summary.ELEVATED_RISK_INDICATOR} Elevated Risk</span>
              )}
              {report.summary.ANOMALOUS > 0 && <span className="aa-status-pill pending">{report.summary.ANOMALOUS} Anomalous</span>}
              {report.summary.UNUSUAL > 0 && <span className="aa-status-pill pending">{report.summary.UNUSUAL} Unusual</span>}
            </div>
            <ul className="aa-course-list">
              {report.indicators.map((ind, i) => (
                <li key={i}>
                  <span className={`aa-status-pill ${SEVERITY_CLASS[ind.severity]}`} style={{ marginRight: "6px" }}>
                    {ind.severity.replace(/_/g, " ")}
                  </span>
                  {ind.explanation}{" "}
                  <button type="button" className="link-button" onClick={() => setExpanded(expanded === i ? null : i)}>
                    {expanded === i ? "Hide evidence" : "Show evidence"}
                  </button>
                  {expanded === i && (
                    <pre style={{ fontSize: "11px", background: "var(--page-bg)", padding: "8px", borderRadius: "6px", overflowX: "auto" }}>
                      {JSON.stringify(ind.evidence, null, 2)}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          </>
        )
      )}
    </section>
  );
}
