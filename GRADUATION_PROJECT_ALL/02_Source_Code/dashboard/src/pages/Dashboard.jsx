import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../AuthContext";
import { api } from "../api/client";
import DoorCard from "../components/DoorCard";
import AlertBanner from "../components/AlertBanner";
import LogsTable from "../components/LogsTable";

const POLL_MS = 5000;

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [doors, setDoors] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [logs, setLogs] = useState([]);
  const [selectedDoorId, setSelectedDoorId] = useState(null);
  const [err, setErr] = useState(null);

  const [showAddDoor, setShowAddDoor] = useState(false);
  const [newDoor, setNewDoor] = useState({ code: "", name: "", building: "", fail_mode: "secure" });
  const [addDoorErr, setAddDoorErr] = useState(null);

  const canOverride = user?.role === "admin";

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

  async function handleOverride(doorId, action) {
    try {
      await api.overrideDoor(doorId, action);
      await refresh();
      if (selectedDoorId === doorId) await refreshLogs(doorId);
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
      setNewDoor({ code: "", name: "", building: "", fail_mode: "secure" });
      setShowAddDoor(false);
      await refresh();
    } catch (e) {
      setAddDoorErr(e.message);
    }
  }

  return (
    <div className="dashboard">
      <header className="topbar">
        <h1>Smart Access Control &mdash; Admin Dashboard</h1>
        <div className="topbar-user">
          <span>{user?.email} ({user?.role})</span>
          <button className="secondary" onClick={logout}>Sign out</button>
        </div>
      </header>

      <main>
        {err && <div className="form-error">{err}</div>}

        <AlertBanner alerts={alerts} onResolve={handleResolve} canResolve={canOverride} />

        {canOverride && (
          <section style={{ margin: "16px 0" }}>
            {!showAddDoor ? (
              <button className="secondary" onClick={() => setShowAddDoor(true)}>
                + Add Door
              </button>
            ) : (
              <form onSubmit={handleAddDoor} style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                <input placeholder="Code (e.g. LAB1)" value={newDoor.code}
                  onChange={(e) => setNewDoor({ ...newDoor, code: e.target.value.toUpperCase() })} />
                <input placeholder="Name (e.g. Lab 1)" value={newDoor.name}
                  onChange={(e) => setNewDoor({ ...newDoor, name: e.target.value })} />
                <input placeholder="Building (e.g. Building A)" value={newDoor.building}
                  onChange={(e) => setNewDoor({ ...newDoor, building: e.target.value })} />
                <select value={newDoor.fail_mode}
                  onChange={(e) => setNewDoor({ ...newDoor, fail_mode: e.target.value })}>
                  <option value="secure">fail-secure</option>
                  <option value="safe">fail-safe</option>
                </select>
                <button type="submit">Save</button>
                <button type="button" className="secondary" onClick={() => { setShowAddDoor(false); setAddDoorErr(null); }}>
                  Cancel
                </button>
                {addDoorErr && <div className="form-error">{addDoorErr}</div>}
              </form>
            )}
          </section>
        )}

        <section className="door-grid">
          {doors.map((door) => (
            <DoorCard
              key={door.door_id}
              door={door}
              canOverride={canOverride}
              onOverride={handleOverride}
              onViewLogs={setSelectedDoorId}
            />
          ))}
        </section>

        <LogsTable
          logs={logs}
          title={selectedDoorId ? `Access Events — Door #${selectedDoorId}` : "Select a door to view history"}
        />
      </main>
    </div>
  );
}