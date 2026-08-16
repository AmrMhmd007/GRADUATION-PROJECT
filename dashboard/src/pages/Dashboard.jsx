import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../AuthContext";
import { api } from "../api/client";
import DoorCard from "../components/DoorCard";
import AlertBanner from "../components/AlertBanner";
import LogsTable from "../components/LogsTable";
import StaffPanel from "../components/StaffPanel";
import AccountMenu from "../components/AccountMenu";

const POLL_MS = 5000;

// Turns "Ahmed Mohamed Ali" into "ahmed.mohamed.ali@AIU.IS" — a starting
// point the admin can still edit by hand before saving, since real name
// collisions (two "Mohamed Ali"s) need a human to disambiguate anyway.
const STAFF_EMAIL_DOMAIN = "AIU.IS";
function suggestEmail(fullName) {
  const slug = fullName
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\s.]/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .join(".");
  return slug ? `${slug}@${STAFF_EMAIL_DOMAIN}` : "";
}

const ADMIN_TABS = [
  { key: "critical", label: "Main Doors" },
  { key: "access", label: "Access Service" },
  { key: "tas", label: "TAs" },
  { key: "doctors", label: "Doctors" },
];

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [doors, setDoors] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [logs, setLogs] = useState([]);
  const [selectedDoorId, setSelectedDoorId] = useState(null);
  const [err, setErr] = useState(null);
  const [activeTab, setActiveTab] = useState("critical");

  const [showAddDoor, setShowAddDoor] = useState(false);
  const [newDoor, setNewDoor] = useState({
    code: "", name: "", building: "", floor: "", fail_mode: "secure", category: "critical",
  });
  const [addDoorErr, setAddDoorErr] = useState(null);
  const [buildings, setBuildings] = useState([]);
  const [showNewBuilding, setShowNewBuilding] = useState(false);
  const [newBuildingName, setNewBuildingName] = useState("");

  const [importBusy, setImportBusy] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importErr, setImportErr] = useState(null);
  const importInputRef = useRef(null);

  const [doorSearch, setDoorSearch] = useState("");

  const canOverride = user?.role === "admin";
  const canRequestAccess = user?.role === "instructor" || user?.role === "doctor";
  const isDoorTab = activeTab === "critical" || activeTab === "access";

  const refresh = useCallback(async () => {
    try {
      const [doorList, alertList] = await Promise.all([
        api.listDoors(),
        api.listAlerts(false),
      ]);
      setDoors(doorList);
      setAlerts(alertList);
      setErr(null);
    } catch (e) {
      setErr(e.message);
    }
  }, []);

  const refreshLogs = useCallback(async (doorId) => {
    if (doorId == null) {
      setLogs([]);
      return;
    }
    try {
      const doorLogs = await api.doorLogs(doorId);
      setLogs(doorLogs);
    } catch (e) {
      setErr(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    refreshLogs(selectedDoorId);
  }, [selectedDoorId, refreshLogs]);

  const loadBuildings = useCallback(async () => {
    try {
      const list = await api.listBuildings();
      setBuildings(list);
    } catch (e) {
      setAddDoorErr(e.message);
    }
  }, []);

  useEffect(() => {
    if (canOverride) loadBuildings();
  }, [canOverride, loadBuildings]);

  async function handleOverride(doorId, action) {
    try {
      await api.overrideDoor(doorId, action);
      await refresh();
      if (selectedDoorId === doorId) await refreshLogs(doorId);
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleRequestAccess(doorId) {
    try {
      await api.requestDoorAccess(doorId);
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleSetStatus(doorId, online) {
    try {
      await api.setDoorStatus(doorId, online);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleDeleteDoor(doorId) {
    try {
      await api.deleteDoor(doorId);
      if (selectedDoorId === doorId) setSelectedDoorId(null);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleResolve(alertId) {
    try {
      await api.resolveAlert(alertId);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleAddDoor(e) {
    e.preventDefault();
    setAddDoorErr(null);
    if (!newDoor.code.trim() || !newDoor.name.trim() || !newDoor.building.trim()) {
      setAddDoorErr("Code, name, and building are all required.");
      return;
    }
    try {
      await api.createDoor(newDoor);
      setNewDoor({
        code: "", name: "", building: "", floor: "", fail_mode: "secure",
        category: activeTab === "access" ? "access_service" : "critical",
      });
      setShowAddDoor(false);
      await refresh();
    } catch (e) {
      setAddDoorErr(e.message);
    }
  }

  async function handleAddBuilding(e) {
    e.preventDefault();
    if (!newBuildingName.trim()) return;
    try {
      const created = await api.createBuilding(newBuildingName.trim());
      setNewBuildingName("");
      setShowNewBuilding(false);
      await loadBuildings();
      setNewDoor((d) => ({ ...d, building: created.name }));
    } catch (e) {
      setAddDoorErr(e.message);
    }
  }

  async function handleImportFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportErr(null);
    setImportResult(null);
    setImportBusy(true);
    try {
      const result = await api.importDoors(file);
      setImportResult(result);
      await refresh();
      await loadBuildings();
    } catch (e) {
      setImportErr(e.message);
    } finally {
      setImportBusy(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  }

  function openAddDoor() {
    setShowAddDoor(true);
    setAddDoorErr(null);
    setShowNewBuilding(false);
    setNewDoor((d) => ({ ...d, category: activeTab === "access" ? "access_service" : "critical" }));
  }

  function selectTab(key) {
    setActiveTab(key);
    setShowAddDoor(false);
    setAddDoorErr(null);
    setDoorSearch("");
  }

  const visibleDoors = (canOverride
    ? doors.filter((d) => d.category === (activeTab === "access" ? "access_service" : "critical"))
    : doors // instructors/doctors only ever see the doors assigned to them
  ).filter((d) => {
    const q = doorSearch.trim().toLowerCase();
    if (!q) return true;
    return (
      d.name.toLowerCase().includes(q) ||
      d.code.toLowerCase().includes(q) ||
      d.building.toLowerCase().includes(q)
    );
  });

  return (
    <div className="dashboard">
      <header className="topbar">
        <div className="topbar-brand">
          <img src="/aiu-logo.png" alt="AIU" className="topbar-logo" />
          <h1>Smart Access Control &mdash; Admin Dashboard</h1>
        </div>
        <div className="topbar-user">
          <AccountMenu />
          <button className="secondary" onClick={logout}>Sign out</button>
        </div>
      </header>

      <main>
        {err && <div className="form-error">{err}</div>}

        <AlertBanner alerts={alerts} onResolve={handleResolve} canResolve={canOverride} />

        {canOverride && (
          <nav className="tab-nav">
            {ADMIN_TABS.map((t) => (
              <button
                key={t.key}
                className={activeTab === t.key ? "tab active" : "tab"}
                onClick={() => selectTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </nav>
        )}

        {canOverride && isDoorTab && (
          <>
            <section style={{ margin: "16px 0" }}>
              {!showAddDoor ? (
                <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
                  <button className="secondary" onClick={openAddDoor}>
                    + Add Door
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
                  onSubmit={handleAddDoor}
                  style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "flex-start" }}
                >
                  <input
                    placeholder="Code (e.g. LAB1)"
                    value={newDoor.code}
                    onChange={(e) => setNewDoor({ ...newDoor, code: e.target.value.toUpperCase() })}
                  />
                  <input
                    placeholder="Name (e.g. Lab 1)"
                    value={newDoor.name}
                    onChange={(e) => setNewDoor({ ...newDoor, name: e.target.value })}
                  />
                  {!showNewBuilding ? (
                    <select
                      value={newDoor.building}
                      onChange={(e) => {
                        if (e.target.value === "__new__") {
                          setShowNewBuilding(true);
                        } else {
                          setNewDoor({ ...newDoor, building: e.target.value });
                        }
                      }}
                    >
                      <option value="">Select a building&hellip;</option>
                      {buildings.map((b) => (
                        <option key={b.building_id} value={b.name}>{b.name}</option>
                      ))}
                      <option value="__new__">+ New building&hellip;</option>
                    </select>
                  ) : (
                    <span style={{ display: "flex", gap: "4px" }}>
                      <input
                        placeholder="New building name"
                        value={newBuildingName}
                        onChange={(e) => setNewBuildingName(e.target.value)}
                      />
                      <button type="button" onClick={handleAddBuilding}>Add</button>
                      <button type="button" className="secondary" onClick={() => { setShowNewBuilding(false); setNewBuildingName(""); }}>
                        Cancel
                      </button>
                    </span>
                  )}
                  <input
                    placeholder="Floor (e.g. Ground, 1, 2)"
                    value={newDoor.floor}
                    onChange={(e) => setNewDoor({ ...newDoor, floor: e.target.value })}
                    style={{ width: "120px" }}
                  />
                  <select
                    value={newDoor.fail_mode}
                    onChange={(e) => setNewDoor({ ...newDoor, fail_mode: e.target.value })}
                  >
                    <option value="secure">fail-secure</option>
                    <option value="safe">fail-safe</option>
                  </select>
                  <select
                    value={newDoor.category}
                    onChange={(e) => setNewDoor({ ...newDoor, category: e.target.value })}
                  >
                    <option value="critical">Main / critical door</option>
                    <option value="access_service">Access service (hall / section room)</option>
                  </select>
                  <button type="submit">Save</button>
                  <button type="button" className="secondary" onClick={() => { setShowAddDoor(false); setAddDoorErr(null); }}>
                    Cancel
                  </button>
                  {addDoorErr && <div className="form-error">{addDoorErr}</div>}
                </form>
              )}
            </section>

            {importErr && <div className="form-error">{importErr}</div>}
            {importResult && (
              <div className="form-success" style={{ marginBottom: "16px" }}>
                Imported {importResult.created} door{importResult.created === 1 ? "" : "s"}.
                {importResult.skipped?.length > 0 && (
                  <> {importResult.skipped.length} skipped (already existed).</>
                )}
                {importResult.errors?.length > 0 && (
                  <> {importResult.errors.length} row{importResult.errors.length === 1 ? "" : "s"} had errors.</>
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

            <div className="door-search">
              <input
                type="search"
                placeholder="Search doors by name, code, or building…"
                value={doorSearch}
                onChange={(e) => setDoorSearch(e.target.value)}
              />
            </div>

            <section className="door-grid">
              {visibleDoors.map((door) => (
                <DoorCard
                  key={door.door_id}
                  door={door}
                  canOverride={canOverride}
                  onOverride={handleOverride}
                  canRequestAccess={false}
                  onRequestAccess={handleRequestAccess}
                  onSetStatus={handleSetStatus}
                  onViewLogs={setSelectedDoorId}
                  onDelete={handleDeleteDoor}
                />
              ))}
              {visibleDoors.length === 0 && (
                <p className="muted">
                  {doorSearch.trim() ? "No doors match your search." : 'No doors in this category yet — use "+ Add Door" above.'}
                </p>
              )}
            </section>

            <LogsTable
              logs={logs}
              title={selectedDoorId ? `Access Events — Door #${selectedDoorId}` : "Select a door to view history"}
            />
          </>
        )}

        {canOverride && activeTab === "tas" && (
          <StaffPanel role="instructor" roleLabel="TA" doors={doors} suggestEmail={suggestEmail} />
        )}

        {canOverride && activeTab === "doctors" && (
          <StaffPanel role="doctor" roleLabel="Doctor" doors={doors} suggestEmail={suggestEmail} />
        )}

        {!canOverride && (
          <>
            {doors.length > 0 && (
              <div className="door-search">
                <input
                  type="search"
                  placeholder="Search doors by name, code, or building…"
                  value={doorSearch}
                  onChange={(e) => setDoorSearch(e.target.value)}
                />
              </div>
            )}
            <section className="door-grid">
              {visibleDoors.map((door) => (
                <DoorCard
                  key={door.door_id}
                  door={door}
                  canOverride={false}
                  onOverride={handleOverride}
                  canRequestAccess={canRequestAccess}
                  onRequestAccess={handleRequestAccess}
                  onSetStatus={handleSetStatus}
                  onViewLogs={setSelectedDoorId}
                />
              ))}
              {doors.length === 0 && (
                <p className="muted">No doors have been assigned to you yet — ask an admin.</p>
              )}
              {doors.length > 0 && visibleDoors.length === 0 && (
                <p className="muted">No doors match your search.</p>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
