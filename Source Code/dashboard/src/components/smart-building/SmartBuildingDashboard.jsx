import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import ZoneCard from "./ZoneCard";
import ZoneDetailModal from "./ZoneDetailModal";
import AutomationLogFeed from "./AutomationLogFeed";
import AutomationRulesPanel from "./AutomationRulesPanel";
import HardwareHealthPanel from "./HardwareHealthPanel";
import SensorPanel from "./SensorPanel";
import MiniBarChart from "./MiniBarChart";
import { formatElapsedSince, formatWatts, OCCUPANCY_LABELS, pickBestSchedule } from "./sbUtils";

const POLL_MS = 5000;
const ZONE_TYPES = ["ROOM", "CLASSROOM", "LAB", "CORRIDOR", "OFFICE", "SERVER_ROOM", "OTHER"];

const SAFETY_STEPS = [
  "Schedule ended",
  "Occupancy check",
  "Verification",
  "No occupants detected",
  "Critical load check",
  "Non-critical shutdown",
  "Device confirmation",
];

export default function SmartBuildingDashboard({ canControl, onInvestigateEvent, focusZoneId, focusZoneToken, onZoneOpenChange }) {
  const [zones, setZones] = useState(null); // null = not loaded yet
  const [summary, setSummary] = useState(null);
  const [logs, setLogs] = useState([]);
  const [sensors, setSensors] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [rules, setRules] = useState([]);
  const [hardwareHealth, setHardwareHealth] = useState([]);
  const [err, setErr] = useState(null);
  const [offline, setOffline] = useState(false);
  // Lazy-initialized from focusZoneId (rather than always starting null) so
  // that when this component first mounts already carrying a deep-linked
  // zone (Dashboard.jsx sets focusZoneId before activeTab flips to "smart"
  // on hydration/popstate), it opens straight to the right zone instead of
  // mounting closed, reporting "closed" back up to Dashboard for a moment,
  // and only then correcting itself — which would otherwise briefly stomp
  // the very hash this modal is being restored from.
  const [openZoneId, setOpenZoneId] = useState(focusZoneId ?? null);
  const [runningPass, setRunningPass] = useState(false);

  const [showAddZone, setShowAddZone] = useState(false);
  const [newZone, setNewZone] = useState({ name: "", zone_type: "CORRIDOR", floor: "" });
  const [addZoneErr, setAddZoneErr] = useState(null);

  const load = useCallback(async () => {
    try {
      const [zoneList, summaryData, logList, sensorList, scheduleList, ruleList, healthList] = await Promise.all([
        api.listZones(),
        api.getAutomationSummary(),
        api.listAutomationLogs(undefined, 200),
        api.listSensors(),
        api.listZoneSchedules(),
        api.listAutomationRules(),
        api.listHardwareHealth(),
      ]);
      setZones(zoneList);
      setSummary(summaryData);
      setLogs(logList);
      setSensors(sensorList);
      setSchedules(scheduleList);
      setRules(ruleList);
      setHardwareHealth(healthList);
      setErr(null);
      setOffline(false);
    } catch (e) {
      setErr(e.message);
      // A network-level failure (backend unreachable) reads differently
      // from a permission/validation error — worth telling the two apart
      // in the empty state.
      setOffline(e.status === undefined);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  // Stage E / E4: "Manage in Smart Building" from RoomProfile jumps straight
  // to that zone's detail modal rather than making the admin re-find it in
  // the grid below. Also the one deep-link restore path: Dashboard.jsx bumps
  // focusZoneToken on hydration/popstate too (see its #tab=smart&zone=<id>
  // handling), with focusZoneId set to null when the hash has no zone param
  // — so this syncs unconditionally (open AND close) rather than only ever
  // opening, letting a hard refresh or Back/Forward restore or clear the
  // modal exactly like the hash says.
  useEffect(() => {
    setOpenZoneId(focusZoneId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusZoneToken]);

  // Reports whichever zone is actually open right now back up to
  // Dashboard.jsx — regardless of whether it was opened from the grid below,
  // from the focusZoneId trigger above, or closed via the modal's own Close
  // button — so Dashboard.jsx can keep the #zone= hash param in sync with
  // reality (see its onZoneOpenChange prop / smartZoneId state).
  useEffect(() => {
    onZoneOpenChange?.(openZoneId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openZoneId]);

  async function handleAddZone(e) {
    e.preventDefault();
    setAddZoneErr(null);
    if (!newZone.name.trim()) {
      setAddZoneErr("Zone name is required.");
      return;
    }
    try {
      await api.createZone({
        name: newZone.name.trim(),
        zone_type: newZone.zone_type,
        floor: newZone.floor.trim() || undefined,
      });
      setNewZone({ name: "", zone_type: "CORRIDOR", floor: "" });
      setShowAddZone(false);
      await load();
    } catch (e2) {
      setAddZoneErr(e2.message);
    }
  }

  async function handleRunPass() {
    setRunningPass(true);
    try {
      await api.runAutomationOnce();
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setRunningPass(false);
    }
  }

  // Loading state — first paint before anything has come back yet.
  if (zones === null && !err) {
    return <p className="muted">Loading Smart Building data…</p>;
  }

  // Backend unreachable / hard failure.
  if (zones === null && err) {
    return (
      <div className="sb-section">
        <p className="sb-empty-state">
          {offline
            ? "Can't reach the backend right now — the Smart Building tab needs the API running."
            : `Couldn't load Smart Building data: ${err}`}
        </p>
      </div>
    );
  }

  const zonesById = new Map(zones.map((z) => [z.zone_id, z]));
  const verifyingZones = zones
    .filter((z) => z.occupancy_state === "VERIFYING")
    .sort((a, b) => new Date(a.verification_started_at) - new Date(b.verification_started_at));
  const primaryVerifying = verifyingZones[0] || null;
  const primarySchedule = primaryVerifying ? pickBestSchedule(schedules, primaryVerifying.zone_id) : null;

  const zonePower = zones.map((z) => ({
    label: z.name,
    value: (z.devices || []).reduce((sum, d) => sum + (d.status ? d.current_power || 0 : 0), 0),
  })).filter((z) => z.value > 0);

  return (
    <div>
      {err && <div className="form-error">{err}</div>}

      {/* ---------------- Building status header ---------------- */}
      <div className="sb-header">
        <div>
          <div className="sb-header-state">
            <span className="dot sb-dot" data-state={summary?.building_state || "UNKNOWN"} style={{ width: "14px", height: "14px" }} />
            <h2>Building: <span className="sb-occupancy-state" data-state={summary?.building_state} style={{ color: "white" }}>
              {OCCUPANCY_LABELS[summary?.building_state] || summary?.building_state || "Unknown"}
            </span></h2>
          </div>
          <div className="sb-header-sub">
            {summary ? `${summary.zones_total} zone${summary.zones_total === 1 ? "" : "s"} monitored` : ""}
          </div>
        </div>
        <div className="sb-header-metrics">
          <div className="sb-header-metric">
            <span className="value">{summary ? `${summary.zones_occupied}/${summary.zones_total}` : "—"}</span>
            <span className="label">Occupied zones</span>
          </div>
          <div className="sb-header-metric">
            <span className="value">{sensors.filter((s) => s.status === "online").length}/{sensors.length}</span>
            <span className="label">Sensors online</span>
          </div>
          <div className="sb-header-metric">
            <span className="value">{summary ? formatWatts(summary.current_power_watts) : "—"}</span>
            <span className="label">Current power</span>
          </div>
          <div className="sb-header-metric">
            <span className="value">{summary ? formatWatts(summary.energy_saved_watts_estimate) : "—"}</span>
            <span className="label">Est. power saved</span>
          </div>
        </div>
      </div>

      {/* ---------------- Summary cards ---------------- */}
      <div className="sb-stat-grid">
        <div className="sb-stat-card accent-green">
          <span className="value">{summary?.zones_occupied ?? "—"}</span>
          <span className="label">Zones occupied</span>
        </div>
        <div className="sb-stat-card">
          <span className="value">{summary?.zones_empty ?? "—"}</span>
          <span className="label">Zones empty</span>
        </div>
        <div className="sb-stat-card accent-amber">
          <span className="value">{summary?.zones_verifying ?? "—"}</span>
          <span className="label">Verifying</span>
        </div>
        <div className="sb-stat-card">
          <span className="value">{summary?.zones_unknown ?? "—"}</span>
          <span className="label">Unknown</span>
        </div>
        <div className="sb-stat-card accent-green">
          <span className="value">{summary?.devices_on ?? "—"}</span>
          <span className="label">Devices ON</span>
        </div>
        <div className="sb-stat-card">
          <span className="value">{summary?.devices_off ?? "—"}</span>
          <span className="label">Devices OFF</span>
        </div>
        <div className="sb-stat-card">
          <span className="value">{summary?.critical_devices_on ?? "—"}</span>
          <span className="label">Critical loads ON</span>
        </div>
        <div className="sb-stat-card accent-red">
          <span className="value">{summary?.active_alerts ?? "—"}</span>
          <span className="label">Active alerts</span>
        </div>
      </div>

      {/* ---------------- Automation status ---------------- */}
      <div className="sb-section">
        <h3>
          Automation Engine
          {canControl && (
            <button className="secondary" disabled={runningPass} onClick={handleRunPass}>
              {runningPass ? "Running…" : "Run pass now"}
            </button>
          )}
        </h3>
        <div className={`sb-automation-card${primaryVerifying ? " is-active" : ""}`}>
          {primaryVerifying ? (
            <>
              <div className="sb-automation-row">
                <div className="sb-automation-field">
                  <div className="label">Status</div>
                  <div className="value">ACTIVE</div>
                </div>
                <div className="sb-automation-field">
                  <div className="label">Current operation</div>
                  <div className="value">Occupancy verification</div>
                </div>
                <div className="sb-automation-field">
                  <div className="label">Zone</div>
                  <div className="value">{primaryVerifying.name}</div>
                </div>
                <div className="sb-automation-field">
                  <div className="label">Verifying for</div>
                  <div className="value">
                    {formatElapsedSince(primaryVerifying.verification_started_at)}
                    {primarySchedule ? ` / ${primarySchedule.verification_minutes}min` : ""}
                  </div>
                </div>
                <div className="sb-automation-field">
                  <div className="label">Decision</div>
                  <div className="value">Waiting for confirmation</div>
                </div>
              </div>
              {verifyingZones.length > 1 && (
                <p className="muted" style={{ margin: "4px 0 0" }}>
                  +{verifyingZones.length - 1} more zone{verifyingZones.length - 1 > 1 ? "s" : ""} also verifying.
                </p>
              )}
            </>
          ) : (
            <p className="sb-automation-idle">
              ACTIVE — monitoring {zones.length} zone{zones.length === 1 ? "" : "s"}, no verification in progress right now.
            </p>
          )}
        </div>
      </div>

      {/* ---------------- Safety sequence (why it doesn't just turn everything off) ---------------- */}
      <div className="sb-section">
        <h3>Building Closing Sequence</h3>
        <div className="sb-safety-flow">
          {SAFETY_STEPS.map((step, i) => {
            // Only meaningfully "active" when a zone is actually verifying —
            // otherwise this is a reference diagram, not a live tracker for
            // a specific zone.
            const activeIndex = primaryVerifying ? 2 : -1; // "Verification" step
            return (
              <span key={step} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span className={`sb-safety-step${i === activeIndex ? " active" : i < activeIndex ? " done" : ""}`}>
                  {step}
                </span>
                {i < SAFETY_STEPS.length - 1 && <span className="sb-safety-arrow">→</span>}
              </span>
            );
          })}
        </div>
        <p className="muted" style={{ margin: "10px 0 0" }}>
          A single empty reading never triggers a shutdown — the engine waits out a full verification window and
          re-checks before acting, and any real occupancy detected in the meantime cancels it immediately.
        </p>
      </div>

      {/* ---------------- Zone grid / building map ---------------- */}
      <div className="sb-section">
        <h3>
          Zones
          {canControl && (
            <button className="secondary" onClick={() => setShowAddZone((v) => !v)}>
              {showAddZone ? "Cancel" : "+ Add zone"}
            </button>
          )}
        </h3>
        {showAddZone && (
          <form onSubmit={handleAddZone} style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "16px" }}>
            <input
              placeholder="Zone name (e.g. Corridor B, Floor 2)"
              value={newZone.name}
              onChange={(e) => setNewZone({ ...newZone, name: e.target.value })}
            />
            <select value={newZone.zone_type} onChange={(e) => setNewZone({ ...newZone, zone_type: e.target.value })}>
              {ZONE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input
              placeholder="Floor (optional)"
              value={newZone.floor}
              onChange={(e) => setNewZone({ ...newZone, floor: e.target.value })}
              style={{ width: "110px" }}
            />
            <button type="submit">Save</button>
            {addZoneErr && <div className="form-error" style={{ width: "100%" }}>{addZoneErr}</div>}
          </form>
        )}
        {zones.length === 0 ? (
          <p className="sb-empty-state">
            No zones configured yet.{canControl ? ' Use "+ Add zone" above to create one (a corridor, lab, or classroom).' : ""}
          </p>
        ) : (
          <div className="sb-zone-grid">
            {zones.map((z) => (
              <ZoneCard key={z.zone_id} zone={z} onOpen={setOpenZoneId} />
            ))}
          </div>
        )}
      </div>

      {/* ---------------- Energy ---------------- */}
      <div className="sb-section">
        <h3>Current Power by Zone</h3>
        <MiniBarChart items={zonePower} formatValue={formatWatts} />
      </div>

      {/* ---------------- Sensors ---------------- */}
      <div className="sb-section">
        <h3>Sensor Monitoring</h3>
        <SensorPanel sensors={sensors} zonesById={zonesById} />
      </div>

      {/* ---------------- Hardware / node health (Stage D / D6, D10) ---------------- */}
      <div className="sb-section">
        <h3>Hardware Node Health</h3>
        <HardwareHealthPanel nodes={hardwareHealth} zonesById={zonesById} />
      </div>

      {/* ---------------- Automation rules (Stage D / D1, D7, D9) ---------------- */}
      <div className="sb-section">
        <h3>Automation Rules</h3>
        <AutomationRulesPanel rules={rules} zones={zones} canControl={canControl} onChanged={load} />
      </div>

      {/* ---------------- Automation log ---------------- */}
      <div className="sb-section">
        <h3>Automation Decision Log</h3>
        <AutomationLogFeed logs={logs} onInvestigateEvent={onInvestigateEvent} />
      </div>

      {openZoneId != null && (
        <ZoneDetailModal zoneId={openZoneId} onClose={() => setOpenZoneId(null)} canControl={canControl} />
      )}
    </div>
  );
}
