import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { fmtDateTime } from "./util";

// Enrollment STATUS only. The backend never exposes templates, so there is
// nothing biometric to browse here — admins can disable/revoke, not view.
export default function FaceIdAdmin() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  const [tick, setTick] = useState(0);
  const load = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    let live = true;
    api.faceStaff().then((r) => { if (live) { setRows(r); setErr(null); } }).catch((e) => { if (live) setErr(e.message); });
    return () => { live = false; };
  }, [tick]);

  async function act(fn, id) {
    try { await fn(id, "Revoked by admin"); load(); } catch (e) { setErr(e.message); }
  }
  if (err) return <div className="form-error">{err}</div>;
  if (!rows) return <p className="muted">Loading…</p>;
  return (
    <div className="ph-table-wrap">
      <p className="ph-small muted">Biometric templates are encrypted and never shown. Staff enroll their own Face ID.</p>
      <table>
        <thead><tr><th>Name</th><th>Role</th><th>Face ID</th><th>Enrolled</th><th>Actions</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.user_id}>
              <td>{r.name}<div className="ph-small muted">{r.email}</div></td>
              <td>{r.role}</td>
              <td>{r.status.replace("_", " ")}</td>
              <td>{r.enrolled_at ? fmtDateTime(r.enrolled_at) : "—"}</td>
              <td className="ph-actions">
                {r.status === "ENROLLED" && <>
                  <button type="button" className="secondary" onClick={() => act(api.faceDisableUser, r.user_id)}>Disable</button>
                  <button type="button" className="secondary" onClick={() => act(api.faceRevokeUser, r.user_id)}>Revoke</button>
                </>}
              </td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan="5" className="muted">No staff in your scope.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
