import { useEffect, useState } from "react";
import { api } from "../../api/client";

// High-risk destructive workflow for permanently deleting a College and its
// dependent academic data. Everything the admin sees here (the impact
// counts) is fetched live from GET /api/faculties/{id}/deletion-impact — no
// hardcoded numbers. Both gates (exact-name match, password) are collected
// here but VERIFIED ONLY by the backend (POST .../cascade-delete) — this
// component never itself decides whether the name or password is correct.
export default function DeleteCollegeModal({ college, onClose, onDeleted }) {
  const [impact, setImpact] = useState(null);
  const [loadErr, setLoadErr] = useState(null);
  const [loading, setLoading] = useState(true);

  const [confirmName, setConfirmName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.getFacultyDeletionImpact(college.faculty_id)
      .then((data) => { if (!cancelled) setImpact(data); })
      .catch((e) => { if (!cancelled) setLoadErr(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [college.faculty_id]);

  const nameMatches = confirmName.trim() === college.name;
  const canSubmit = nameMatches && password.length > 0 && !busy && !loading && !loadErr;

  async function handleDelete() {
    if (!canSubmit) return;
    setBusy(true);
    setErr(null);
    try {
      await api.cascadeDeleteFaculty(college.faculty_id, confirmName.trim(), password);
      onDeleted();
    } catch (e) {
      setErr(e.message);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  const rows = impact ? [
    ["Departments", impact.departments],
    ["Doctors / Instructors", impact.doctors],
    ["Teaching Assistants", impact.teaching_assistants],
    ["Courses", impact.courses],
    ["Course Assignments", impact.course_assignments],
    ["Admin scope grants", impact.admin_scopes],
    ["Operational scope grants", impact.operational_scopes],
  ] : [];

  return (
    <div className="aa-modal-backdrop aa-danger-modal" onClick={(e) => e.target === e.currentTarget && !busy && onClose()}>
      <div className="aa-modal" style={{ maxWidth: 480 }}>
        <h3>Delete "{college.name}"?</h3>

        <div className="aa-danger-banner">
          This action permanently deletes the college and its dependent academic data. This action cannot be undone.
        </div>

        {loading && <p className="muted">Loading impact summary&hellip;</p>}
        {loadErr && <div className="form-error">{loadErr}</div>}

        {impact && (
          <>
            <p style={{ fontSize: 13 }}>Deleting this college will permanently remove:</p>
            <ul className="aa-impact-list">
              {rows.map(([label, value]) => (
                <li key={label}><span>{label}</span><strong>{value}</strong></li>
              ))}
            </ul>
            <p className="muted" style={{ fontSize: 12 }}>
              Doctors and Teaching Assistants in this college keep their accounts and login — they are only
              unassigned from the academic organization, exactly like the "Remove from academic org" action.
              Audit history for this college is preserved.
            </p>
          </>
        )}

        <label style={{ display: "block", marginTop: 14, fontSize: 13, fontWeight: 600 }}>
          Type the college name (<code>{college.name}</code>) to confirm
        </label>
        <input
          value={confirmName}
          onChange={(e) => setConfirmName(e.target.value)}
          placeholder={college.name}
          disabled={busy}
          autoFocus
        />

        <label style={{ display: "block", marginTop: 12, fontSize: 13, fontWeight: 600 }}>
          Re-enter your admin password
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          disabled={busy}
        />

        {err && <div className="form-error" style={{ marginTop: 10 }}>{err}</div>}

        <div className="aa-confirm-actions" style={{ marginTop: 16 }}>
          <button type="button" className="secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button
            type="button"
            className="danger-highrisk"
            onClick={handleDelete}
            disabled={!canSubmit}
          >
            {busy ? "Deleting…" : "Delete College"}
          </button>
        </div>
      </div>
    </div>
  );
}
