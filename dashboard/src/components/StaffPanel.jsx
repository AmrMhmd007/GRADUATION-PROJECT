import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";

// Reusable "add + manage door access" panel for a staff role — used for both
// the TAs tab and the Doctors tab so the two don't duplicate the same form
// and assignment logic twice.
export default function StaffPanel({ role, roleLabel, doors, suggestEmail }) {
  const [showAdd, setShowAdd] = useState(false);
  const [newStaff, setNewStaff] = useState({ name: "", email: "", password: "", faculty_id: "" });
  const [addErr, setAddErr] = useState(null);
  const [addOk, setAddOk] = useState(null);

  const [faculties, setFaculties] = useState([]);
  const [showNewFaculty, setShowNewFaculty] = useState(false);
  const [newFacultyName, setNewFacultyName] = useState("");

  const [staffList, setStaffList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState("");
  const [assignedDoors, setAssignedDoors] = useState([]);
  const [assignDoorId, setAssignDoorId] = useState("");
  const [manageErr, setManageErr] = useState(null);

  const [importBusy, setImportBusy] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importErr, setImportErr] = useState(null);
  const importInputRef = useRef(null);

  async function loadFaculties() {
    try {
      const list = await api.listFaculties();
      setFaculties(list);
    } catch (e) {
      setAddErr(e.message);
    }
  }

  useEffect(() => {
    loadFaculties();
  }, []);

  async function handleAddFaculty(e) {
    e.preventDefault();
    if (!newFacultyName.trim()) return;
    try {
      const created = await api.createFaculty(newFacultyName.trim());
      setNewFacultyName("");
      setShowNewFaculty(false);
      await loadFaculties();
      setNewStaff((s) => ({ ...s, faculty_id: String(created.faculty_id) }));
    } catch (e) {
      setAddErr(e.message);
    }
  }

  async function loadStaff() {
    try {
      const all = await api.listUsers();
      setStaffList(all.filter((u) => u.role === role));
    } catch (e) {
      setManageErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    setSelectedId("");
    setAssignedDoors([]);
    setShowAdd(false);
    setNewStaff({ name: "", email: "", password: "", faculty_id: "" });
    setImportResult(null);
    setImportErr(null);
    loadStaff();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  async function handleImportFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportErr(null);
    setImportResult(null);
    setImportBusy(true);
    try {
      const result = await api.importUsers(file, role);
      setImportResult(result);
      await loadStaff();
    } catch (e) {
      setImportErr(e.message);
    } finally {
      setImportBusy(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  }

  async function loadAssignedDoors(id) {
    if (!id) {
      setAssignedDoors([]);
      return;
    }
    try {
      const assignments = await api.listDoorAssignments(id);
      setAssignedDoors(assignments);
    } catch (e) {
      setManageErr(e.message);
    }
  }

  async function handleSelectId(id) {
    setSelectedId(id);
    setManageErr(null);
    await loadAssignedDoors(id);
  }

  async function handleAdd(e) {
    e.preventDefault();
    setAddErr(null);
    setAddOk(null);
    if (!newStaff.name.trim() || !newStaff.email.trim() || !newStaff.password) {
      setAddErr("Name, email, and password are all required.");
      return;
    }
    if (!newStaff.faculty_id) {
      setAddErr(`Pick which faculty this ${roleLabel} is enrolled in first.`);
      return;
    }
    try {
      const created = await api.createUser({
        name: newStaff.name.trim(),
        email: newStaff.email.trim(),
        role,
        password: newStaff.password,
        faculty_id: Number(newStaff.faculty_id),
      });
      setAddOk(`Added ${created.name} (${created.email}). Give them this email + the password you set.`);
      setNewStaff({ name: "", email: "", password: "", faculty_id: "" });
      setShowAdd(false);
      await loadStaff();
    } catch (e) {
      setAddErr(e.message);
    }
  }

  async function handleAssign(e) {
    e.preventDefault();
    setManageErr(null);
    if (!selectedId || !assignDoorId) {
      setManageErr(`Pick a ${roleLabel} and a door first.`);
      return;
    }
    try {
      await api.addDoorAssignment(selectedId, assignDoorId);
      setAssignDoorId("");
      await loadAssignedDoors(selectedId);
    } catch (e) {
      setManageErr(e.message);
    }
  }

  async function handleRemove(assignmentId) {
    try {
      await api.removeDoorAssignment(selectedId, assignmentId);
      await loadAssignedDoors(selectedId);
    } catch (e) {
      setManageErr(e.message);
    }
  }

  async function handleDeleteStaff(userId) {
    const staff = staffList.find((s) => String(s.user_id) === String(userId));
    const label = staff ? `${staff.name} (${staff.email})` : `this ${roleLabel}`;
    if (!window.confirm(`Remove ${label}? This deletes their account and door access — it can't be undone.`)) {
      return;
    }
    setManageErr(null);
    try {
      await api.deleteUser(userId);
      if (String(selectedId) === String(userId)) {
        setSelectedId("");
        setAssignedDoors([]);
      }
      await loadStaff();
    } catch (e) {
      setManageErr(e.message);
    }
  }

  const assignedIds = new Set(assignedDoors.map((a) => a.door_id));
  const unassignedDoors = doors.filter((d) => !assignedIds.has(d.door_id));

  return (
    <div>
      {addOk && <div className="form-success" style={{ margin: "8px 0" }}>{addOk}</div>}

      <section style={{ margin: "16px 0" }}>
        {!showAdd ? (
          <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
            <button className="secondary" onClick={() => { setShowAdd(true); setAddOk(null); }}>
              + Add {roleLabel}
            </button>
            <label className="secondary" style={{ display: "inline-block", cursor: "pointer" }}>
              {importBusy ? "Importing…" : "Import from Excel"}
              <input
                ref={importInputRef}
                type="file"
                accept=".xlsx,.xlsm"
                onChange={handleImportFile}
                disabled={importBusy}
                style={{ display: "none" }}
              />
            </label>
          </div>
        ) : (
          <form
            onSubmit={handleAdd}
            style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "flex-start", marginBottom: "8px" }}
          >
            <input
              placeholder="Full name (e.g. Ahmed Mohamed Ali)"
              value={newStaff.name}
              onChange={(e) => {
                const name = e.target.value;
                setNewStaff((prev) => ({
                  ...prev,
                  name,
                  email: prev.email === suggestEmail(prev.name) ? suggestEmail(name) : prev.email,
                }));
              }}
            />
            <input
              placeholder="Email (auto-filled, editable)"
              value={newStaff.email}
              onChange={(e) => setNewStaff({ ...newStaff, email: e.target.value })}
            />
            <input
              type="text"
              placeholder={`Password (${roleLabel} picks this, you type it in)`}
              value={newStaff.password}
              onChange={(e) => setNewStaff({ ...newStaff, password: e.target.value })}
            />
            {!showNewFaculty ? (
              <select
                value={newStaff.faculty_id}
                onChange={(e) => {
                  if (e.target.value === "__new__") {
                    setShowNewFaculty(true);
                  } else {
                    setNewStaff({ ...newStaff, faculty_id: e.target.value });
                  }
                }}
              >
                <option value="">Select faculty enrolled in&hellip;</option>
                {faculties.map((f) => (
                  <option key={f.faculty_id} value={f.faculty_id}>{f.name}</option>
                ))}
                <option value="__new__">+ New faculty&hellip;</option>
              </select>
            ) : (
              <span style={{ display: "flex", gap: "4px" }}>
                <input
                  placeholder="New faculty name"
                  value={newFacultyName}
                  onChange={(e) => setNewFacultyName(e.target.value)}
                />
                <button type="button" onClick={handleAddFaculty}>Add</button>
                <button type="button" className="secondary" onClick={() => { setShowNewFaculty(false); setNewFacultyName(""); }}>
                  Cancel
                </button>
              </span>
            )}
            <button type="submit">Save</button>
            <button type="button" className="secondary" onClick={() => { setShowAdd(false); setAddErr(null); }}>
              Cancel
            </button>
            {addErr && <div className="form-error">{addErr}</div>}
          </form>
        )}
      </section>

      {importErr && <div className="form-error">{importErr}</div>}
      {importResult && (
        <div className="form-success" style={{ margin: "8px 0" }}>
          Added {importResult.created.length} {roleLabel}{importResult.created.length === 1 ? "" : "s"}.
          {importResult.skipped?.length > 0 && <> {importResult.skipped.length} skipped (email already existed).</>}
          {importResult.errors?.length > 0 && <> {importResult.errors.length} row{importResult.errors.length === 1 ? "" : "s"} had errors.</>}

          {importResult.created.length > 0 && (
            <div style={{ overflowX: "auto", marginTop: "8px" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", padding: "4px" }}>Name</th>
                    <th style={{ textAlign: "left", padding: "4px" }}>Email</th>
                    <th style={{ textAlign: "left", padding: "4px" }}>Password</th>
                  </tr>
                </thead>
                <tbody>
                  {importResult.created.map((c, i) => (
                    <tr key={i}>
                      <td style={{ padding: "4px" }}>{c.name}</td>
                      <td style={{ padding: "4px" }}>{c.email}</td>
                      <td style={{ padding: "4px", fontFamily: "monospace" }}>{c.password}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted" style={{ marginTop: "4px" }}>
                Copy these out now — passwords aren't recoverable later.
              </p>
            </div>
          )}

          {(importResult.skipped?.length > 0 || importResult.errors?.length > 0) && (
            <ul style={{ margin: "6px 0 0", paddingLeft: "18px" }}>
              {[...importResult.skipped, ...importResult.errors].map((line, i) => (
                <li key={i} style={{ fontSize: "12px" }}>{line}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <section style={{ margin: "16px 0" }}>
        <div style={{ border: "1px solid #e5e7eb", borderRadius: "8px", padding: "12px" }}>
          {!loading && staffList.length === 0 && (
            <p className="muted">No {roleLabel}s yet &mdash; add one above.</p>
          )}

          {staffList.length > 0 && (
            <ul className="staff-row-list">
              {staffList.map((s) => (
                <li
                  key={s.user_id}
                  className={String(selectedId) === String(s.user_id) ? "staff-row staff-row-active" : "staff-row"}
                >
                  <span className="staff-row-info">
                    {s.name} ({s.email}){s.faculty_name ? ` — ${s.faculty_name}` : ""}
                  </span>
                  <span className="staff-row-actions">
                    <button type="button" className="link-button" onClick={() => handleSelectId(s.user_id)}>
                      Manage doors
                    </button>
                    <button type="button" className="link-button" onClick={() => handleDeleteStaff(s.user_id)}>
                      Remove
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}

          {selectedId && (
            <div style={{ marginTop: "12px" }}>
              <strong>Assigned doors:</strong>
              {assignedDoors.length === 0 ? (
                <p style={{ color: "#6b7280" }}>No doors assigned yet.</p>
              ) : (
                <ul>
                  {assignedDoors.map((a) => (
                    <li key={a.assignment_id}>
                      {a.door_name} ({a.door_code}){" "}
                      <button className="link-button" onClick={() => handleRemove(a.assignment_id)}>
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <form onSubmit={handleAssign} style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
                <select value={assignDoorId} onChange={(e) => setAssignDoorId(e.target.value)}>
                  <option value="">Select a door to assign&hellip;</option>
                  {unassignedDoors.map((d) => (
                    <option key={d.door_id} value={d.door_id}>
                      {d.name} ({d.code})
                    </option>
                  ))}
                </select>
                <button type="submit">Assign</button>
              </form>
            </div>
          )}

          {manageErr && <div className="form-error" style={{ marginTop: "8px" }}>{manageErr}</div>}
        </div>
      </section>
    </div>
  );
}
