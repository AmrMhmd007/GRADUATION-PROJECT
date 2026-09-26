import { useState } from "react";
import { api } from "../../api/client";

// Same stroke-only "department" glyph as AcademicOverview.jsx's ScopeIcon /
// GlobalSearch.jsx's EntityIcon — kept identical across all three so a
// department reads as the same entity everywhere in the app.
function DepartmentIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <rect x="4" y="4" width="16" height="16" rx="1.2" />
      <path d="M8 9h8M8 13h8M8 17h5" strokeLinecap="round" />
    </svg>
  );
}

// Departments within a selected college — same "professional scope card"
// pattern as CollegeGrid, one level deeper. Counts/code/description/status
// come straight from the backend's DepartmentOut
// (app/routers/academic.py::_department_with_counts).
export default function DepartmentGrid({ college, departments, onSelect, onBack, onCreated }) {
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

  async function handleAdd(e) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await api.createDepartment(college.faculty_id, {
        name: form.name.trim(), code: form.code.trim() || null, description: form.description.trim() || null,
      });
      setForm({ name: "", code: "", description: "" });
      setShowAdd(false);
      await onCreated();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function startEdit(d) {
    setEditingId(d.department_id);
    setEditForm({ name: d.name, code: d.code || "", description: d.description || "" });
    setEditErr(null);
  }

  async function saveEdit(departmentId) {
    setEditBusy(true);
    setEditErr(null);
    try {
      await api.updateDepartment(departmentId, {
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

  async function toggleStatus(d) {
    try {
      await api.updateDepartment(d.department_id, { status: d.status === "active" ? "inactive" : "active" });
      await onCreated();
    } catch (e) {
      setErr(e.message);
    }
  }

  const visible = departments
    .filter((d) => statusFilter === "all" || d.status === statusFilter)
    .filter((d) => {
      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return d.name.toLowerCase().includes(q) || (d.code || "").toLowerCase().includes(q);
    });

  return (
    <div>
      <div className="aa-section-header">
        <div>
          <button type="button" className="link-button" style={{ paddingLeft: 0 }} onClick={onBack}>
            &larr; All colleges
          </button>
          <h2 className="aa-title">{college.name}{college.code ? <span className="aa-code-badge">{college.code}</span> : null}</h2>
          {college.description && <p className="aa-subtitle">{college.description}</p>}
        </div>
        <button className="secondary" type="button" onClick={() => setShowAdd((v) => !v)}>
          {showAdd ? "Cancel" : "+ Add Department"}
        </button>
      </div>

      <div className="aa-summary-row">
        <div className="aa-summary-stat"><span className="value">{departments.length}</span><span className="label">Departments</span></div>
        <div className="aa-summary-stat"><span className="value">{departments.reduce((s, d) => s + (d.doctors_count || 0), 0)}</span><span className="label">Doctors/Instructors</span></div>
        <div className="aa-summary-stat"><span className="value">{departments.reduce((s, d) => s + (d.tas_count || 0), 0)}</span><span className="label">Teaching Assistants</span></div>
        <div className="aa-summary-stat"><span className="value">{departments.reduce((s, d) => s + (d.courses_count || 0), 0)}</span><span className="label">Courses</span></div>
      </div>

      {showAdd && (
        <form className="aa-inline-form aa-inline-form-wide" onSubmit={handleAdd}>
          <input
            placeholder="Department name (e.g. Electronics & Communication Engineering)"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            autoFocus
          />
          <input
            placeholder="Code (e.g. ECE)"
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
        <input className="aa-search" placeholder="Search departments by name or code…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </div>

      {departments.length === 0 && !showAdd && (
        <p className="muted">No departments in {college.name} yet &mdash; add one above.</p>
      )}
      {departments.length > 0 && visible.length === 0 && (
        <p className="muted">No departments match your search/filter.</p>
      )}

      <div className="aa-card-grid">
        {visible.map((d) => (
          <div key={d.department_id} className="aa-scope-card aa-scope-card-block">
            {editingId === d.department_id ? (
              <div className="aa-inline-edit" onClick={(e) => e.stopPropagation()}>
                <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} placeholder="Name" />
                <input value={editForm.code} onChange={(e) => setEditForm({ ...editForm, code: e.target.value })} placeholder="Code" style={{ maxWidth: 100 }} />
                <input value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} placeholder="Description" />
                {editErr && <div className="form-error">{editErr}</div>}
                <div className="aa-confirm-actions">
                  <button type="button" className="secondary" onClick={() => setEditingId(null)} disabled={editBusy}>Cancel</button>
                  <button type="button" onClick={() => saveEdit(d.department_id)} disabled={editBusy}>{editBusy ? "Saving…" : "Save"}</button>
                </div>
              </div>
            ) : (
              <>
                <button type="button" className="aa-scope-card-clickzone" onClick={() => onSelect(d)}>
                  <div className="aa-scope-card-icon"><DepartmentIcon /></div>
                  <div className="aa-scope-card-body">
                    <h3>{d.name}{d.code ? <span className="aa-code-badge">{d.code}</span> : null}</h3>
                    {d.description && <p className="aa-scope-card-desc">{d.description}</p>}
                    <p className="aa-scope-card-meta">
                      {d.doctors_count || 0} doctor{(d.doctors_count || 0) === 1 ? "" : "s"}
                      {" · "}{d.tas_count || 0} TA{(d.tas_count || 0) === 1 ? "" : "s"}
                      {" · "}{d.courses_count || 0} course{(d.courses_count || 0) === 1 ? "" : "s"}
                    </p>
                  </div>
                  <div className="aa-scope-card-arrow" aria-hidden="true">→</div>
                </button>
                <div className="aa-card-footer">
                  <span className={`aa-status-pill ${d.status === "active" ? "active" : "expired"}`}>
                    {d.status === "active" ? "Active" : "Inactive"}
                  </span>
                  <span className="aa-card-footer-actions">
                    <button type="button" className="link-button" onClick={() => startEdit(d)}>Edit</button>
                    <button type="button" className="link-button" onClick={() => toggleStatus(d)}>
                      {d.status === "active" ? "Deactivate" : "Activate"}
                    </button>
                  </span>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
