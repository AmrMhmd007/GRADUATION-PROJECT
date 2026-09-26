import { useEffect, useState } from "react";
import { api } from "../../api/client";
import ConfirmDialog from "./ConfirmDialog";

// Global Departments Management — every department across every college,
// with the same rollup counts (doctors/TAs/courses) FacultyOut/DepartmentOut
// already compute server-side. Add/Edit/Activate-Deactivate/Delete reuse
// the exact CRUD endpoints ManageOrgModal.jsx already used for departments;
// this is the same capability presented as a dedicated page rather than a
// side panel inside a modal, per the requested navigation redesign.
export default function DepartmentsManagement({ colleges, onChanged, onOpenCollegeContext }) {
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  const [collegeFilter, setCollegeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ faculty_id: "", name: "", code: "", description: "" });
  const [addErr, setAddErr] = useState(null);
  const [addBusy, setAddBusy] = useState(false);

  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ name: "", code: "", description: "", status: "active" });
  const [editErr, setEditErr] = useState(null);
  const [editBusy, setEditBusy] = useState(false);

  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleteErr, setDeleteErr] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const rows = await api.listDepartments(collegeFilter || undefined);
      setDepartments(rows);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collegeFilter]);

  async function handleAdd(e) {
    e.preventDefault();
    setAddErr(null);
    if (!form.faculty_id) { setAddErr("Choose a college."); return; }
    if (!form.name.trim()) { setAddErr("Department name is required."); return; }
    setAddBusy(true);
    try {
      await api.createDepartment(Number(form.faculty_id), {
        name: form.name.trim(), code: form.code.trim() || null, description: form.description.trim() || null,
      });
      setForm({ faculty_id: "", name: "", code: "", description: "" });
      setShowAdd(false);
      await load();
      onChanged?.();
    } catch (e) {
      setAddErr(e.message);
    } finally {
      setAddBusy(false);
    }
  }

  function startEdit(d) {
    setEditingId(d.department_id);
    setEditForm({ name: d.name, code: d.code || "", description: d.description || "", status: d.status || "active" });
    setEditErr(null);
  }

  async function saveEdit(deptId) {
    setEditBusy(true);
    setEditErr(null);
    try {
      await api.updateDepartment(deptId, {
        name: editForm.name.trim(), code: editForm.code.trim() || null,
        description: editForm.description.trim() || null, status: editForm.status,
      });
      setEditingId(null);
      await load();
      onChanged?.();
    } catch (e) {
      setEditErr(e.message);
    } finally {
      setEditBusy(false);
    }
  }

  async function toggleStatus(d) {
    try {
      await api.updateDepartment(d.department_id, { status: d.status === "active" ? "inactive" : "active" });
      await load();
      onChanged?.();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleDelete(d) {
    setDeleteBusy(true);
    setDeleteErr(null);
    try {
      await api.deleteDepartment(d.department_id);
      setConfirmDelete(null);
      await load();
      onChanged?.();
    } catch (e) {
      setDeleteErr(e.message);
      setConfirmDelete(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  const visible = departments
    .filter((d) => statusFilter === "all" || (d.status || "active") === statusFilter)
    .filter((d) => {
      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return d.name.toLowerCase().includes(q) || (d.code || "").toLowerCase().includes(q) || (d.faculty_name || "").toLowerCase().includes(q);
    });

  return (
    <div>
      <div className="aa-section-header">
        <div>
          <h2 className="aa-title">Departments</h2>
          <p className="aa-subtitle">Every department across every college you're authorized to manage.</p>
        </div>
        <button className="secondary" type="button" onClick={() => setShowAdd((v) => !v)}>
          {showAdd ? "Cancel" : "+ Add Department"}
        </button>
      </div>

      {showAdd && (
        <form className="aa-inline-form aa-inline-form-wide" onSubmit={handleAdd} style={{ flexWrap: "wrap" }}>
          <select value={form.faculty_id} onChange={(e) => setForm({ ...form, faculty_id: e.target.value })}>
            <option value="">— Choose college —</option>
            {colleges.map((c) => <option key={c.faculty_id} value={c.faculty_id}>{c.name}</option>)}
          </select>
          <input placeholder="Department name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="Code (optional)" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} style={{ maxWidth: 120 }} />
          <input placeholder="Description (optional)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <button type="submit" disabled={addBusy}>{addBusy ? "Saving…" : "Save"}</button>
          {addErr && <div className="form-error" style={{ width: "100%" }}>{addErr}</div>}
        </form>
      )}

      <div className="aa-toolbar">
        <input className="aa-search" placeholder="Search departments by name, code, or college…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={collegeFilter} onChange={(e) => setCollegeFilter(e.target.value)}>
          <option value="">All colleges</option>
          {colleges.map((c) => <option key={c.faculty_id} value={c.faculty_id}>{c.name}</option>)}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </div>

      {err && <div className="form-error">{err}</div>}
      {deleteErr && <div className="form-error">{deleteErr}</div>}

      {loading ? (
        <p className="muted">Loading&hellip;</p>
      ) : visible.length === 0 ? (
        <p className="muted">No departments match your search/filter.</p>
      ) : (
        <table className="aa-data-table">
          <thead>
            <tr>
              <th>Department</th><th>College</th><th>Doctors</th><th>TAs</th>
              <th>Courses</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((d) => (
              editingId === d.department_id ? (
                <tr key={d.department_id}>
                  <td colSpan={7}>
                    <div className="aa-inline-edit">
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} placeholder="Name" style={{ flex: 1, minWidth: 180 }} />
                        <input value={editForm.code} onChange={(e) => setEditForm({ ...editForm, code: e.target.value })} placeholder="Code" style={{ maxWidth: 120 }} />
                        <select value={editForm.status} onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}>
                          <option value="active">Active</option>
                          <option value="inactive">Inactive</option>
                        </select>
                      </div>
                      <input value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} placeholder="Description" />
                      {editErr && <div className="form-error">{editErr}</div>}
                      <div className="aa-confirm-actions">
                        <button type="button" className="secondary" onClick={() => setEditingId(null)} disabled={editBusy}>Cancel</button>
                        <button type="button" onClick={() => saveEdit(d.department_id)} disabled={editBusy}>{editBusy ? "Saving…" : "Save"}</button>
                      </div>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={d.department_id} className="aa-clickable-row"
                    onClick={() => onOpenCollegeContext(colleges.find((c) => c.faculty_id === d.faculty_id) || { faculty_id: d.faculty_id, name: d.faculty_name }, d)}>
                  <td><strong>{d.name}</strong>{d.code ? <span className="aa-code-badge">{d.code}</span> : null}</td>
                  <td>{d.faculty_name}</td>
                  <td>{d.doctors_count || 0}</td>
                  <td>{d.tas_count || 0}</td>
                  <td>{d.courses_count || 0}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <span className={`aa-status-pill ${d.status === "inactive" ? "expired" : "active"}`}>{d.status === "inactive" ? "Inactive" : "Active"}</span>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <span className="aa-card-footer-actions">
                      <button type="button" className="link-button" onClick={() => startEdit(d)}>Edit</button>
                      <button type="button" className="link-button" onClick={() => toggleStatus(d)}>
                        {d.status === "active" ? "Deactivate" : "Activate"}
                      </button>
                      <button type="button" className="link-button aa-danger-text" onClick={() => setConfirmDelete(d)}>Delete</button>
                    </span>
                  </td>
                </tr>
              )
            ))}
          </tbody>
        </table>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title={`Delete ${confirmDelete.name}?`}
          message="This can't be undone. Departments that still have courses, staff, or scope grants can't be deleted — remove or reassign those first."
          confirmLabel="Delete"
          busy={deleteBusy}
          onConfirm={() => handleDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
