import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import ScheduledAccessSection from "./ScheduledAccessSection";
import StaffAnomalySection from "./StaffAnomalySection";
import ConfirmDialog from "./ConfirmDialog";

// The exact 6 academic titles the backend's CheckConstraint/Pydantic
// validator allows (schemas.ACADEMIC_TITLES) — deliberately hardcoded here
// rather than re-derived, since this is a closed, backend-enforced set.
const ACADEMIC_TITLES = [
  "Professor", "Associate Professor", "Assistant Professor",
  "Lecturer", "Instructor", "Teaching Assistant",
];

// Professional Doctor/TA profile panel: Name, Role, College, Department,
// Courses, Assigned Areas, Access Permissions, Status, plus (Phase 8) an
// editable academic profile — staff_id/academic_title/specialization/phone/
// status via PUT /api/users/{id}/staff-profile, the one endpoint the user
// explicitly required this go through (no new endpoint).
//
// Note (documented limitation, not silently omitted): "Recent Access"
// activity would need access events joined by user rather than by door —
// the existing AccessEvent model is door/credential-keyed. That join isn't
// built yet, so it's left out here rather than faked.
export default function StaffProfile({ staff, college, department, onClose, onStaffRemoved, onStaffUpdated }) {
  const [assignedDoors, setAssignedDoors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  // Real audit activity for this staff member (GET /api/audit-logs, Phase 12
  // added resource_id filtering) — only an unrestricted admin can read it
  // (routers/audit_logs.py); a scoped admin gets a 403, which we treat as
  // "not available to you" and hide entirely rather than show as an error,
  // since it isn't this admin's fault and isn't actionable for them.
  const [auditActivity, setAuditActivity] = useState(null);
  const [auditAvailable, setAuditAvailable] = useState(true);
  const [confirmingRemove, setConfirmingRemove] = useState(false);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeErr, setRemoveErr] = useState(null);

  // Reassign to a different College/Department (PUT /api/users/{id}/scope —
  // already existed on the backend and in client.js, but had no UI to drive
  // it: the only "Add" flow fixes the college/department to whatever
  // department view you're already in, with no way to move a staff member
  // afterward).
  const [reassigning, setReassigning] = useState(false);
  const [faculties, setFaculties] = useState(null);
  const [depts, setDepts] = useState([]);
  const [reassignFacultyId, setReassignFacultyId] = useState(college?.faculty_id || "");
  const [reassignDeptId, setReassignDeptId] = useState(department?.department_id || "");
  const [reassignErr, setReassignErr] = useState(null);
  const [reassignBusy, setReassignBusy] = useState(false);

  // Remove from the academic organization entirely (college/department ->
  // NULL) — POST /api/users/{id}/unassign. Deliberately separate from the
  // "Remove {roleLabel}" button below, which deletes the account itself.
  const [confirmingUnassign, setConfirmingUnassign] = useState(false);
  const [unassignBusy, setUnassignBusy] = useState(false);
  const [unassignErr, setUnassignErr] = useState(null);

  const hasAcademicAssignment = Boolean(staff.faculty_id || college);

  useEffect(() => {
    if (!reassigning || faculties !== null) return;
    api.listFaculties().then(setFaculties).catch(() => setFaculties([]));
  }, [reassigning, faculties]);

  useEffect(() => {
    if (!reassigning || !reassignFacultyId) { setDepts([]); return; }
    let cancelled = false;
    api.listDepartments(reassignFacultyId).then((rows) => { if (!cancelled) setDepts(rows); }).catch(() => { if (!cancelled) setDepts([]); });
    return () => { cancelled = true; };
  }, [reassigning, reassignFacultyId]);

  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState(() => ({
    name: staff.name || "",
    staff_id: staff.staff_id || "",
    academic_title: staff.academic_title || "",
    specialization: staff.specialization || "",
    phone: staff.phone || "",
    status: staff.status || "active",
  }));
  const [editErr, setEditErr] = useState(null);
  const [editBusy, setEditBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.listDoorAssignments(staff.user_id)
      .then((rows) => { if (!cancelled) setAssignedDoors(rows); })
      .catch((e) => { if (!cancelled) setErr(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [staff.user_id]);

  useEffect(() => {
    let cancelled = false;
    api.listAuditLogs({ resource_type: "user", resource_id: staff.user_id, limit: 10 })
      .then((rows) => { if (!cancelled) setAuditActivity(rows); })
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 403) setAuditAvailable(false);
        else setAuditActivity([]); // some other failure — show the section as empty rather than break the profile
      });
    return () => { cancelled = true; };
  }, [staff.user_id]);

  const roleLabel = staff.role === "doctor" ? "Doctor" : "Teaching Assistant";

  async function handleRemove() {
    setRemoveBusy(true);
    setRemoveErr(null);
    try {
      await api.deleteUser(staff.user_id);
      setConfirmingRemove(false);
      onStaffRemoved?.(staff);
      onClose();
    } catch (e) {
      setRemoveErr(e.message);
      setConfirmingRemove(false);
    } finally {
      setRemoveBusy(false);
    }
  }

  async function handleReassign(e) {
    e.preventDefault();
    if (!reassignFacultyId) {
      setReassignErr("Pick a college.");
      return;
    }
    setReassignBusy(true);
    setReassignErr(null);
    try {
      // updateStaffScope only ever SETS faculty_id/department_id when given
      // — it can't clear a field back to null (that's exactly why
      // unassignStaff exists as its own endpoint). So moving to a
      // *different* college first needs a real clear of the old
      // department_id, or a stale department from the old college could be
      // left dangling underneath the new one. Crossing colleges therefore
      // unassigns first, then re-assigns to the new college/department —
      // two real, audited steps rather than one endpoint pretending to do
      // both. Moving departments within the same college doesn't need this.
      if (staff.faculty_id && Number(reassignFacultyId) !== staff.faculty_id) {
        await api.unassignStaff(staff.user_id);
      }
      await api.updateStaffScope(staff.user_id, {
        faculty_id: Number(reassignFacultyId),
        ...(reassignDeptId ? { department_id: Number(reassignDeptId) } : {}),
      });
      setReassigning(false);
      await onStaffUpdated?.();
      onClose();
    } catch (e) {
      setReassignErr(e.message);
    } finally {
      setReassignBusy(false);
    }
  }

  async function handleUnassign() {
    setUnassignBusy(true);
    setUnassignErr(null);
    try {
      await api.unassignStaff(staff.user_id);
      setConfirmingUnassign(false);
      await onStaffUpdated?.();
      onClose();
    } catch (e) {
      setUnassignErr(e.message);
      setConfirmingUnassign(false);
    } finally {
      setUnassignBusy(false);
    }
  }

  async function handleSaveProfile(e) {
    e.preventDefault();
    setEditBusy(true);
    setEditErr(null);
    try {
      await api.updateStaffProfile(staff.user_id, {
        name: editForm.name.trim(),
        staff_id: editForm.staff_id.trim() || null,
        academic_title: editForm.academic_title || null,
        specialization: editForm.specialization.trim() || null,
        phone: editForm.phone.trim() || null,
        status: editForm.status,
      });
      setEditing(false);
      await onStaffUpdated?.();
    } catch (e) {
      setEditErr(e.message);
    } finally {
      setEditBusy(false);
    }
  }

  return (
    <div className="aa-modal-backdrop" onClick={onClose}>
      <div className="aa-modal" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="aa-modal-close" onClick={onClose} aria-label="Close">×</button>

        <div className="aa-profile-header">
          <div className="aa-staff-card-avatar large" aria-hidden="true">
            {staff.name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase()}
          </div>
          <div style={{ flex: 1 }}>
            <h2>{staff.name}{staff.staff_id ? <span className="aa-code-badge">{staff.staff_id}</span> : null}</h2>
            <p className="aa-profile-role">
              {roleLabel}{staff.academic_title ? ` · ${staff.academic_title}` : ""} &middot;{" "}
              {hasAcademicAssignment ? <>{department?.name || "(no department)"} &middot; {college?.name}</> : "Unassigned (no college/department)"}
            </p>
            <span className={`aa-status-pill ${staff.status === "inactive" ? "expired" : "active"}`}>
              {staff.status === "inactive" ? "Inactive" : "Active"}
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
            <button type="button" className="link-button" onClick={() => { setEditing((v) => !v); setEditErr(null); }}>
              {editing ? "Cancel edit" : "Edit profile"}
            </button>
            <button
              type="button"
              className="link-button"
              onClick={() => { setReassigning((v) => !v); setReassignErr(null); }}
            >
              {reassigning ? "Cancel reassign" : "Assign / Reassign"}
            </button>
            {hasAcademicAssignment && (
              <button
                type="button"
                className="link-button aa-danger-text"
                onClick={() => setConfirmingUnassign(true)}
              >
                Remove from academic org
              </button>
            )}
            <button
              type="button"
              className="link-button aa-danger-text"
              onClick={() => setConfirmingRemove(true)}
            >
              Delete {roleLabel} account
            </button>
          </div>
        </div>

        {removeErr && <div className="form-error">{removeErr}</div>}
        {unassignErr && <div className="form-error">{unassignErr}</div>}

        {reassigning && (
          <form className="aa-inline-edit" onSubmit={handleReassign} style={{ marginBottom: 18 }}>
            <label className="hint">College</label>
            <select
              value={reassignFacultyId}
              onChange={(e) => { setReassignFacultyId(e.target.value); setReassignDeptId(""); }}
            >
              <option value="">— Select a college —</option>
              {(faculties || []).map((f) => (
                <option key={f.faculty_id} value={f.faculty_id}>{f.name}</option>
              ))}
            </select>

            <label className="hint">Department (optional — college-level assignment if left blank)</label>
            <select
              value={reassignDeptId}
              onChange={(e) => setReassignDeptId(e.target.value)}
              disabled={!reassignFacultyId}
            >
              <option value="">— No specific department —</option>
              {depts.map((d) => (
                <option key={d.department_id} value={d.department_id}>{d.name}</option>
              ))}
            </select>

            {reassignErr && <div className="form-error">{reassignErr}</div>}
            <div className="aa-confirm-actions">
              <button type="button" className="secondary" onClick={() => setReassigning(false)} disabled={reassignBusy}>Cancel</button>
              <button type="submit" disabled={reassignBusy}>{reassignBusy ? "Saving…" : "Save assignment"}</button>
            </div>
          </form>
        )}

        {editing ? (
          <form className="aa-inline-edit" onSubmit={handleSaveProfile} style={{ marginBottom: 18 }}>
            <label className="hint">Full name</label>
            <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} />

            <label className="hint">Staff ID</label>
            <input value={editForm.staff_id} onChange={(e) => setEditForm({ ...editForm, staff_id: e.target.value })} placeholder="e.g. DR-2031" />

            <label className="hint">Academic title (distinct from system role — {roleLabel})</label>
            <select value={editForm.academic_title} onChange={(e) => setEditForm({ ...editForm, academic_title: e.target.value })}>
              <option value="">— None set —</option>
              {ACADEMIC_TITLES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>

            <label className="hint">Specialization</label>
            <input value={editForm.specialization} onChange={(e) => setEditForm({ ...editForm, specialization: e.target.value })} placeholder="e.g. Digital Signal Processing" />

            <label className="hint">Phone</label>
            <input value={editForm.phone} onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })} />

            <label className="hint">Status</label>
            <select value={editForm.status} onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>

            {editErr && <div className="form-error">{editErr}</div>}
            <div className="aa-confirm-actions">
              <button type="button" className="secondary" onClick={() => setEditing(false)} disabled={editBusy}>Cancel</button>
              <button type="submit" disabled={editBusy}>{editBusy ? "Saving…" : "Save profile"}</button>
            </div>
          </form>
        ) : (
          <dl className="aa-profile-grid">
            <div><dt>Email</dt><dd>{staff.email}</dd></div>
            <div><dt>College</dt><dd>{college?.name || "Unassigned"}</dd></div>
            <div><dt>Department</dt><dd>{department?.name || "Unassigned"}</dd></div>
            <div><dt>Staff ID</dt><dd>{staff.staff_id || "—"}</dd></div>
            <div><dt>Academic title</dt><dd>{staff.academic_title || "—"}</dd></div>
            <div><dt>Specialization</dt><dd>{staff.specialization || "—"}</dd></div>
            <div><dt>Phone</dt><dd>{staff.phone || "—"}</dd></div>
          </dl>
        )}

        <section className="aa-profile-section">
          <h3>Assigned Courses</h3>
          {(staff.assigned_courses || []).length === 0 ? (
            <p className="muted">No courses assigned.</p>
          ) : (
            <ul className="aa-course-list">
              {staff.assigned_courses.map((c) => (
                <li key={c.course_id}><strong>{c.code}</strong> &mdash; {c.name}</li>
              ))}
            </ul>
          )}
        </section>

        <section className="aa-profile-section">
          <h3>Assigned Areas / Access Permissions</h3>
          {loading && <p className="muted">Loading&hellip;</p>}
          {err && <div className="form-error">{err}</div>}
          {!loading && !err && (
            assignedDoors.length === 0 ? (
              <p className="muted">No rooms assigned yet.</p>
            ) : (
              <ul className="aa-course-list">
                {assignedDoors.map((a) => (
                  <li key={a.assignment_id}>{a.door_name} ({a.door_code})</li>
                ))}
              </ul>
            )
          )}
        </section>

        <ScheduledAccessSection staff={staff} />
        <StaffAnomalySection staff={staff} />

        {auditAvailable && (
          <section className="aa-profile-section">
            <h3>Recent Audit Activity</h3>
            {auditActivity === null ? (
              <p className="muted">Loading&hellip;</p>
            ) : auditActivity.length === 0 ? (
              <p className="muted">No recorded admin/security actions on this account.</p>
            ) : (
              <ul className="aa-course-list">
                {auditActivity.map((r) => (
                  <li key={r.log_id}>
                    <span className={`aa-status-pill ${r.result === "failure" ? "expired" : "active"}`} style={{ marginRight: 6, fontSize: 10 }}>
                      {r.result}
                    </span>
                    {r.actor_email || "System"} {r.action} &middot;{" "}
                    <span className="muted">{new Date(r.timestamp + "Z").toLocaleString()}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {confirmingRemove && (
          <ConfirmDialog
            title={`Delete ${staff.name}'s account?`}
            message={`This permanently deletes their account and door assignments. Access history stays on record but is no longer linked to a name. This can't be undone. (This is different from "Remove from academic org" — that keeps the account but clears the college/department.)`}
            confirmLabel="Delete account"
            busy={removeBusy}
            onConfirm={handleRemove}
            onCancel={() => setConfirmingRemove(false)}
          />
        )}

        {confirmingUnassign && (
          <ConfirmDialog
            title={`Remove ${staff.name} from the academic organization?`}
            message={`This clears their college and department (both become "Unassigned"). Their account, login, and door assignments are kept — this can be undone later by reassigning them. If they have active course assignments, this will be blocked until those are reassigned or removed.`}
            confirmLabel="Remove from org"
            busy={unassignBusy}
            onConfirm={handleUnassign}
            onCancel={() => setConfirmingUnassign(false)}
          />
        )}
      </div>
    </div>
  );
}
