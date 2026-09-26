import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import ConfirmDialog from "./ConfirmDialog";

// "Manage Colleges & Departments" — a professional admin panel reachable
// from Academic Administration's college view. Left pane: colleges (add,
// rename, delete). Right pane: departments of the selected college (add,
// rename, delete). Delete is blocked server-side whenever dependents exist
// (departments/staff/courses/scope grants) — this UI surfaces that 409
// as a clear message rather than silently failing.
export default function ManageOrgModal({ onClose, onChanged }) {
  const [colleges, setColleges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [notice, setNotice] = useState(null); // { kind: "success"|"error", text }

  const [selectedCollege, setSelectedCollege] = useState(null);
  const [departments, setDepartments] = useState([]);
  const [deptLoading, setDeptLoading] = useState(false);

  const [newCollegeName, setNewCollegeName] = useState("");
  const [editingCollegeId, setEditingCollegeId] = useState(null);
  const [editingCollegeName, setEditingCollegeName] = useState("");

  const [newDeptName, setNewDeptName] = useState("");
  const [editingDeptId, setEditingDeptId] = useState(null);
  const [editingDeptName, setEditingDeptName] = useState("");

  const [confirmTarget, setConfirmTarget] = useState(null); // { kind: "college"|"department", id, name }
  const [deleteBusy, setDeleteBusy] = useState(false);

  async function loadColleges() {
    setLoading(true);
    setErr(null);
    try {
      const list = await api.listFaculties();
      setColleges(list);
      if (selectedCollege) {
        const stillThere = list.find((c) => c.faculty_id === selectedCollege.faculty_id);
        setSelectedCollege(stillThere || null);
      }
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadDepartments(faculty_id) {
    setDeptLoading(true);
    try {
      const list = await api.listDepartments(faculty_id);
      setDepartments(list);
    } catch (e) {
      setErr(e.message);
    } finally {
      setDeptLoading(false);
    }
  }

  useEffect(() => {
    loadColleges();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedCollege) loadDepartments(selectedCollege.faculty_id);
    else setDepartments([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCollege?.faculty_id]);

  function flash(kind, text) {
    setNotice({ kind, text });
    window.clearTimeout(flash._t);
    flash._t = window.setTimeout(() => setNotice(null), 4000);
  }

  // ---- Colleges ----
  async function handleAddCollege(e) {
    e.preventDefault();
    if (!newCollegeName.trim()) return;
    try {
      await api.createFaculty(newCollegeName.trim());
      setNewCollegeName("");
      await loadColleges();
      onChanged?.();
      flash("success", "College added.");
    } catch (e) {
      flash("error", e.message);
    }
  }

  async function handleRenameCollege(id) {
    if (!editingCollegeName.trim()) return;
    try {
      await api.updateFaculty(id, editingCollegeName.trim());
      setEditingCollegeId(null);
      await loadColleges();
      onChanged?.();
      flash("success", "College renamed.");
    } catch (e) {
      flash("error", e.message);
    }
  }

  async function handleDeleteCollege(id, name) {
    setDeleteBusy(true);
    try {
      await api.deleteFaculty(id);
      setConfirmTarget(null);
      await loadColleges();
      onChanged?.();
      flash("success", `"${name}" deleted.`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e.message;
      flash("error", msg);
      setConfirmTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  // ---- Departments ----
  async function handleAddDepartment(e) {
    e.preventDefault();
    if (!newDeptName.trim() || !selectedCollege) return;
    try {
      await api.createDepartment(selectedCollege.faculty_id, newDeptName.trim());
      setNewDeptName("");
      await loadDepartments(selectedCollege.faculty_id);
      onChanged?.();
      flash("success", "Department added.");
    } catch (e) {
      flash("error", e.message);
    }
  }

  async function handleRenameDepartment(id) {
    if (!editingDeptName.trim()) return;
    try {
      await api.updateDepartment(id, { name: editingDeptName.trim() });
      setEditingDeptId(null);
      await loadDepartments(selectedCollege.faculty_id);
      onChanged?.();
      flash("success", "Department renamed.");
    } catch (e) {
      flash("error", e.message);
    }
  }

  async function handleDeleteDepartment(id, name) {
    setDeleteBusy(true);
    try {
      await api.deleteDepartment(id);
      setConfirmTarget(null);
      await loadDepartments(selectedCollege.faculty_id);
      onChanged?.();
      flash("success", `"${name}" deleted.`);
    } catch (e) {
      flash("error", e.message);
      setConfirmTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="aa-modal-backdrop" onClick={onClose}>
      <div className="aa-modal aa-manage-modal" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="aa-modal-close" onClick={onClose} aria-label="Close">×</button>
        <h2 className="aa-title">Manage Colleges &amp; Departments</h2>
        <p className="aa-subtitle">Add, rename, or remove colleges and their departments. Deleting is blocked while staff, courses, or sub-departments still depend on it.</p>

        {notice && <div className={notice.kind === "success" ? "form-success" : "form-error"}>{notice.text}</div>}
        {err && <div className="form-error">{err}</div>}

        <div className="aa-manage-columns">
          <div className="aa-manage-column">
            <h4>Colleges</h4>
            <form className="aa-inline-form" onSubmit={handleAddCollege}>
              <input placeholder="New college name" value={newCollegeName} onChange={(e) => setNewCollegeName(e.target.value)} />
              <button type="submit">Add</button>
            </form>
            {loading ? (
              <p className="muted">Loading&hellip;</p>
            ) : colleges.length === 0 ? (
              <p className="muted">No colleges yet.</p>
            ) : (
              <ul className="aa-manage-list">
                {colleges.map((c) => (
                  <li
                    key={c.faculty_id}
                    className={selectedCollege?.faculty_id === c.faculty_id ? "aa-manage-row active" : "aa-manage-row"}
                  >
                    {editingCollegeId === c.faculty_id ? (
                      <>
                        <input
                          value={editingCollegeName}
                          onChange={(e) => setEditingCollegeName(e.target.value)}
                          autoFocus
                        />
                        <span className="aa-manage-row-actions">
                          <button type="button" className="link-button" onClick={() => handleRenameCollege(c.faculty_id)}>Save</button>
                          <button type="button" className="link-button" onClick={() => setEditingCollegeId(null)}>Cancel</button>
                        </span>
                      </>
                    ) : (
                      <>
                        <button type="button" className="aa-manage-row-label" onClick={() => setSelectedCollege(c)}>
                          {c.name}
                        </button>
                        <span className="aa-manage-row-actions">
                          <button
                            type="button"
                            className="link-button"
                            onClick={() => { setEditingCollegeId(c.faculty_id); setEditingCollegeName(c.name); }}
                          >
                            Rename
                          </button>
                          <button
                            type="button"
                            className="link-button"
                            onClick={() => setConfirmTarget({ kind: "college", id: c.faculty_id, name: c.name })}
                          >
                            Delete
                          </button>
                        </span>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="aa-manage-column">
            <h4>Departments{selectedCollege ? ` — ${selectedCollege.name}` : ""}</h4>
            {!selectedCollege ? (
              <p className="muted">Select a college on the left to manage its departments.</p>
            ) : (
              <>
                <form className="aa-inline-form" onSubmit={handleAddDepartment}>
                  <input placeholder="New department name" value={newDeptName} onChange={(e) => setNewDeptName(e.target.value)} />
                  <button type="submit">Add</button>
                </form>
                {deptLoading ? (
                  <p className="muted">Loading&hellip;</p>
                ) : departments.length === 0 ? (
                  <p className="muted">No departments in this college yet.</p>
                ) : (
                  <ul className="aa-manage-list">
                    {departments.map((d) => (
                      <li key={d.department_id} className="aa-manage-row">
                        {editingDeptId === d.department_id ? (
                          <>
                            <input value={editingDeptName} onChange={(e) => setEditingDeptName(e.target.value)} autoFocus />
                            <span className="aa-manage-row-actions">
                              <button type="button" className="link-button" onClick={() => handleRenameDepartment(d.department_id)}>Save</button>
                              <button type="button" className="link-button" onClick={() => setEditingDeptId(null)}>Cancel</button>
                            </span>
                          </>
                        ) : (
                          <>
                            <span className="aa-manage-row-label" style={{ cursor: "default" }}>{d.name}</span>
                            <span className="aa-manage-row-actions">
                              <button
                                type="button"
                                className="link-button"
                                onClick={() => { setEditingDeptId(d.department_id); setEditingDeptName(d.name); }}
                              >
                                Rename
                              </button>
                              <button
                                type="button"
                                className="link-button"
                                onClick={() => setConfirmTarget({ kind: "department", id: d.department_id, name: d.name })}
                              >
                                Delete
                              </button>
                            </span>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {confirmTarget && (
        <ConfirmDialog
          title={`Delete ${confirmTarget.kind === "college" ? "college" : "department"} "${confirmTarget.name}"?`}
          message={
            confirmTarget.kind === "college"
              ? "This can't be undone. Colleges that still have departments, staff, or scope grants can't be deleted — remove or reassign those first."
              : "This can't be undone. Departments that still have courses, staff, or scope grants can't be deleted — remove or reassign those first."
          }
          busy={deleteBusy}
          onCancel={() => setConfirmTarget(null)}
          onConfirm={() =>
            confirmTarget.kind === "college"
              ? handleDeleteCollege(confirmTarget.id, confirmTarget.name)
              : handleDeleteDepartment(confirmTarget.id, confirmTarget.name)
          }
        />
      )}
    </div>
  );
}
