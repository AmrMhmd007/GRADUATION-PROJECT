import { useState } from "react";
import { api } from "../../api/client";
import DeleteCollegeModal from "./DeleteCollegeModal";

// Same stroke-only "college" glyph as AcademicOverview.jsx's ScopeIcon /
// GlobalSearch.jsx's EntityIcon — kept identical across all three so a
// college reads as the same entity everywhere in the app.
function CollegeIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M2.5 9 12 4.5 21.5 9 12 13.5 2.5 9Z" strokeLinejoin="round" />
      <path d="M6.5 11v4.2c0 1.6 2.5 3.3 5.5 3.3s5.5-1.7 5.5-3.3V11" strokeLinejoin="round" />
    </svg>
  );
}

// "Select Academic Scope" — professional college cards. All counts
// (departments/doctors/TAs/courses) and status/code/description come
// straight from the backend's FacultyOut (app/routers/faculties.py::_with_counts)
// — nothing here is computed or guessed on the frontend.
export default function CollegeGrid({ colleges, onSelect, onCreated, onManage }) {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", code: "", description: "" });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ name: "", code: "", description: "" });
  const [editErr, setEditErr] = useState(null);
  const [editBusy, setEditBusy] = useState(false);
  const [deletingCollege, setDeletingCollege] = useState(null);

  async function handleAdd(e) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await api.createFaculty({ name: form.name.trim(), code: form.code.trim() || null, description: form.description.trim() || null });
      setForm({ name: "", code: "", description: "" });
      setShowAdd(false);
      await onCreated();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function startEdit(c) {
    setEditingId(c.faculty_id);
    setEditForm({ name: c.name, code: c.code || "", description: c.description || "" });
    setEditErr(null);
  }

  async function saveEdit(facultyId) {
    setEditBusy(true);
    setEditErr(null);
    try {
      await api.updateFaculty(facultyId, {
        name: editForm.name.trim(), code: editForm.code.trim() || null, description: editForm.description.trim() || null,
      });
      setEditingId(null);
      await onCreated();
    } catch (e) {
      setEditErr(e.message);
    } finally {
      setEditBusy(false);
    }
  }

  async function toggleStatus(c) {
    try {
      await api.updateFaculty(c.faculty_id, { status: c.status === "active" ? "inactive" : "active" });
      await onCreated();
    } catch (e) {
      setErr(e.message);
    }
  }

  const visible = colleges
    .filter((c) => statusFilter === "all" || c.status === statusFilter)
    .filter((c) => {
      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return c.name.toLowerCase().includes(q) || (c.code || "").toLowerCase().includes(q);
    });

  return (
    <div>
      <div className="aa-section-header">
        <div>
          {/* This used to repeat "Academic Administration" here too — the
              exact workspace-level title the shared WorkspaceHeader (and,
              above it, the sidebar) already show once. "Colleges" is this
              section's own real title, not a duplicate of the workspace's. */}
          <h2 className="aa-title">Colleges</h2>
          <p className="aa-subtitle">Add colleges, and drill into their departments, staff, and courses.</p>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <button className="secondary" type="button" onClick={onManage}>
            Manage Colleges &amp; Departments
          </button>
          <button className="secondary" type="button" onClick={() => setShowAdd((v) => !v)}>
            {showAdd ? "Cancel" : "+ Add College"}
          </button>
        </div>
      </div>

      <div className="aa-summary-row">
        <div className="aa-summary-stat"><span className="value">{colleges.length}</span><span className="label">Colleges</span></div>
        <div className="aa-summary-stat"><span className="value">{colleges.reduce((sum, c) => sum + (c.departments_count || 0), 0)}</span><span className="label">Departments</span></div>
        <div className="aa-summary-stat"><span className="value">{colleges.reduce((sum, c) => sum + (c.doctors_count || 0), 0)}</span><span className="label">Doctors/Instructors</span></div>
        <div className="aa-summary-stat"><span className="value">{colleges.reduce((sum, c) => sum + (c.tas_count || 0), 0)}</span><span className="label">Teaching Assistants</span></div>
        <div className="aa-summary-stat"><span className="value">{colleges.reduce((sum, c) => sum + (c.courses_count || 0), 0)}</span><span className="label">Courses</span></div>
      </div>

      {showAdd && (
        <form className="aa-inline-form aa-inline-form-wide" onSubmit={handleAdd}>
          <input
            placeholder="College name (e.g. Faculty of Engineering)"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            autoFocus
          />
          <input
            placeholder="Code (e.g. ENG)"
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
            style={{ maxWidth: 120 }}
          />
          <input
            placeholder="Description (optional)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <button type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </form>
      )}
      {err && <div className="form-error">{err}</div>}

      <div className="aa-toolbar">
        <input className="aa-search" placeholder="Search colleges by name or code…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </div>

      {colleges.length === 0 && !showAdd && (
        <p className="muted">No colleges set up yet &mdash; add one above.</p>
      )}
      {colleges.length > 0 && visible.length === 0 && (
        <p className="muted">No colleges match your search/filter.</p>
      )}

      <div className="aa-card-grid">
        {visible.map((c) => (
          <div key={c.faculty_id} className="aa-scope-card aa-scope-card-block">
            {editingId === c.faculty_id ? (
              <div className="aa-inline-edit" onClick={(e) => e.stopPropagation()}>
                <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} placeholder="Name" />
                <input value={editForm.code} onChange={(e) => setEditForm({ ...editForm, code: e.target.value })} placeholder="Code" style={{ maxWidth: 100 }} />
                <input value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} placeholder="Description" />
                {editErr && <div className="form-error">{editErr}</div>}
                <div className="aa-confirm-actions">
                  <button type="button" className="secondary" onClick={() => setEditingId(null)} disabled={editBusy}>Cancel</button>
                  <button type="button" onClick={() => saveEdit(c.faculty_id)} disabled={editBusy}>{editBusy ? "Saving…" : "Save"}</button>
                </div>
              </div>
            ) : (
              <>
                <button type="button" className="aa-scope-card-clickzone" onClick={() => onSelect(c)}>
                  <div className="aa-scope-card-icon"><CollegeIcon /></div>
                  <div className="aa-scope-card-body">
                    <h3>{c.name}{c.code ? <span className="aa-code-badge">{c.code}</span> : null}</h3>
                    {c.description && <p className="aa-scope-card-desc">{c.description}</p>}
                    <p className="aa-scope-card-meta">
                      {c.departments_count || 0} dept{(c.departments_count || 0) === 1 ? "" : "s"}
                      {" · "}{c.doctors_count || 0} doctor{(c.doctors_count || 0) === 1 ? "" : "s"}
                      {" · "}{c.tas_count || 0} TA{(c.tas_count || 0) === 1 ? "" : "s"}
                      {" · "}{c.courses_count || 0} course{(c.courses_count || 0) === 1 ? "" : "s"}
                    </p>
                  </div>
                  <div className="aa-scope-card-arrow" aria-hidden="true">→</div>
                </button>
                <div className="aa-card-footer">
                  <span className={`aa-status-pill ${c.status === "active" ? "active" : "expired"}`}>
                    {c.status === "active" ? "Active" : "Inactive"}
                  </span>
                  <span className="aa-card-footer-actions">
                    <button type="button" className="link-button" onClick={() => startEdit(c)}>Edit</button>
                    <button type="button" className="link-button" onClick={() => toggleStatus(c)}>
                      {c.status === "active" ? "Deactivate" : "Activate"}
                    </button>
                    <button type="button" className="link-button aa-danger-text" onClick={() => setDeletingCollege(c)}>
                      Delete
                    </button>
                  </span>
                </div>
              </>
            )}
          </div>
        ))}
      </div>

      {deletingCollege && (
        <DeleteCollegeModal
          college={deletingCollege}
          onClose={() => setDeletingCollege(null)}
          onDeleted={async () => {
            setDeletingCollege(null);
            await onCreated();
          }}
        />
      )}
    </div>
  );
}
