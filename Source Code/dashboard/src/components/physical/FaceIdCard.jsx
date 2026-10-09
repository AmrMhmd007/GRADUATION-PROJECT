import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { SourceBadge } from "./Badges";
import { fmtDateTime } from "./util";

// Self-service Face ID status for Doctors/TAs. Capture itself needs an
// embedding adapter on an enrollment device; this card reports that
// honestly instead of faking a camera flow. No template is ever fetched.
export default function FaceIdCard() {
  const [status, setStatus] = useState(null);
  const [caps, setCaps] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    Promise.all([api.faceMe(), api.faceCapabilities()])
      .then(([s, c]) => { if (live) { setStatus(s); setCaps(c); setErr(null); } })
      .catch((e) => { if (live) setErr(e.message); });
    return () => { live = false; };
  }, [tick]);

  async function revoke() {
    setBusy(true);
    try {
      await api.faceRevokeMe("self-revoked");
      setTick((t) => t + 1);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (err) return <section className="ph-card"><div className="form-error">{err}</div></section>;
  if (!status || !caps) return <section className="ph-card"><p className="muted">Loading Face ID…</p></section>;

  const enrolled = status.status === "ENROLLED";
  return (
    <section className="ph-card" aria-labelledby="faceid-h">
      <div className="ph-card-head">
        <h3 id="faceid-h">Face ID</h3>
        <span className="ph-pill" data-state={enrolled ? "HEALTHY" : "UNKNOWN"}>{status.status.replace("_", " ")}</span>
      </div>
      {enrolled ? (
        <p className="ph-small">
          Enrolled {fmtDateTime(status.enrolled_at)} · <SourceBadge source={status.source} />. Door access also
          requires your room authorization and a valid schedule.
        </p>
      ) : (
        <p className="ph-small">
          Set up Face ID to enter authorized rooms. Face recognition alone never grants access.
        </p>
      )}
      <p className="ph-small muted">
        Face capture: <strong>{caps.capture_status}</strong>. {caps.note}
      </p>
      <div className="ph-actions">
        {!enrolled && (
          <button type="button" disabled title={caps.capture_available ? "Use the enrollment station" : caps.note}>
            Set Up Face ID
          </button>
        )}
        {enrolled && (
          <button type="button" className="secondary" onClick={revoke} disabled={busy}>
            {busy ? "Revoking…" : "Revoke my Face ID"}
          </button>
        )}
      </div>
    </section>
  );
}
