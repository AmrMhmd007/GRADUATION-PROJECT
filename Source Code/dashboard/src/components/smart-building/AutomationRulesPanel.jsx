import { useState } from "react";
import { api } from "../../api/client";

// Stage D / D1, D7, D9 — the backend has had full AutomationRule CRUD
// (GET/POST/PUT/DELETE /api/automation/rules) since Phase 4, each mutation
// already audited via AuditLog (see routers/zones.py) — but until now there
// was no UI for it at all, only the read-only decision log below. This is
// real, persistent configuration: enabling/disabling here changes exactly
// what services/automation_engine.py's resolve_rule() picks up on its next
// pass, nothing simulated.
//
// Only one trigger/action pair is implemented by the engine today
// (CONFIRMED_EMPTY -> SHUTDOWN_NON_CRITICAL — see automation_engine.py's own
// docstring), and the backend's create_automation_rule already rejects any
// other trigger with a 400. The create form matches that reality instead of
// offering a "second, not real yet" rule type in the UI.
export default function AutomationRulesPanel({ rules, zones, canControl, onChanged }) {
  const [showForm, setShowForm] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [err, setErr] = useState(null);
  const [form, setForm] = useState({
    name: "", zone_id: "", priority: 0, grace_period_minutes: "", minimum_confidence: 0,
  });

  async function handleToggle(rule) {
    setErr(null);
    setBusyId(rule.rule_id);
    try {
      await api.updateAutomationRule(rule.rule_id, { enabled: !rule.enabled });
      await onChanged();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(rule) {
    setErr(null);
    setBusyId(rule.rule_id);
    try {
      await api.deleteAutomationRule(rule.rule_id);
      await onChanged();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleCreate(e) {
    e.preventDefault();
    setErr(null);
    if (!form.name.trim()) {
      setErr("Rule name is required.");
      return;
    }
    try {
      await api.createAutomationRule({
        name: form.name.trim(),
        zone_id: form.zone_id ? Number(form.zone_id) : null,
        priority: Number(form.priority) || 0,
        conditions: { trigger: "CONFIRMED_EMPTY" },
        actions: { action: "SHUTDOWN_NON_CRITICAL" },
        grace_period_minutes: form.grace_period_minutes ? Number(form.grace_period_minutes) : null,
        minimum_confidence: Number(form.minimum_confidence) || 0,
      });
      setForm({ name: "", zone_id: "", priority: 0, grace_period_minutes: "", minimum_confidence: 0 });
      setShowForm(false);
      await onChanged();
    } catch (e2) {
      setErr(e2.message);
    }
  }

  return (
    <div>
      {err && <div className="form-error">{err}</div>}
      {canControl && (
        <button type="button" className="secondary" style={{ marginBottom: "10px" }} onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancel" : "+ New rule"}
        </button>
      )}
      {showForm && (
        <form onSubmit={handleCreate} style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "16px" }}>
          <input
            placeholder="Rule name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <select value={form.zone_id} onChange={(e) => setForm({ ...form, zone_id: e.target.value })}>
            <option value="">Building-wide (all zones)</option>
            {(zones || []).map((z) => <option key={z.zone_id} value={z.zone_id}>{z.name}</option>)}
          </select>
          <input
            type="number" placeholder="Priority" value={form.priority} style={{ width: "90px" }}
            onChange={(e) => setForm({ ...form, priority: e.target.value })}
          />
          <input
            type="number" placeholder="Grace period (min, optional)" value={form.grace_period_minutes}
            style={{ width: "180px" }}
            onChange={(e) => setForm({ ...form, grace_period_minutes: e.target.value })}
          />
          <input
            type="number" step="0.05" min="0" max="1" placeholder="Min. confidence (0-1)"
            value={form.minimum_confidence} style={{ width: "160px" }}
            onChange={(e) => setForm({ ...form, minimum_confidence: e.target.value })}
          />
          <button type="submit">Save</button>
          <p className="muted" style={{ width: "100%", margin: 0 }}>
            Trigger/action are fixed to "confirmed empty → shut down non-critical loads" — the only rule type the
            automation engine implements today.
          </p>
        </form>
      )}

      {rules.length === 0 ? (
        <p className="sb-empty-state">
          No automation rules configured — the engine falls back to its built-in default (shut down non-critical
          loads once a zone is confirmed empty past its schedule) for every zone.
        </p>
      ) : (
        // Same horizontal-overflow containment already used by Access Events
        // and Sensor Monitoring (see .table-scroll in App.css) — the table
        // stays full-width and readable, and only its own container scrolls
        // sideways on narrow viewports, not the page.
        <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Zone</th>
              <th>Priority</th>
              <th>Grace period</th>
              <th>Min. confidence</th>
              <th>Status</th>
              {canControl && <th></th>}
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.rule_id}>
                <td>{r.name}</td>
                <td>{r.zone_name || "Building-wide"}</td>
                <td>{r.priority}</td>
                <td>{r.grace_period_minutes != null ? `${r.grace_period_minutes}m` : <span className="muted">Uses schedule</span>}</td>
                <td>{r.minimum_confidence}</td>
                <td className={r.enabled ? "ok" : "muted"}>{r.enabled ? "Enabled" : "Disabled"}</td>
                {canControl && (
                  <td style={{ display: "flex", gap: "6px" }}>
                    <button type="button" className="secondary" disabled={busyId === r.rule_id} onClick={() => handleToggle(r)}>
                      {r.enabled ? "Disable" : "Enable"}
                    </button>
                    <button type="button" className="danger" disabled={busyId === r.rule_id} onClick={() => handleDelete(r)}>
                      Delete
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}
