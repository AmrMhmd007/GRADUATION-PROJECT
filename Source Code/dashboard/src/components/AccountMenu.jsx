import { useRef, useState } from "react";
import { useAuth } from "../AuthContext";
import { api, mediaUrl, setToken, ApiError } from "../api/client";

function initialsOf(nameOrEmail) {
  if (!nameOrEmail) return "?";
  const base = nameOrEmail.includes("@") ? nameOrEmail.split("@")[0] : nameOrEmail;
  const parts = base.trim().split(/\s+/).filter(Boolean);
  const letters = parts.slice(0, 2).map((p) => p[0].toUpperCase());
  return letters.join("") || "?";
}

export default function AccountMenu() {
  const { user, refreshProfile } = useAuth();
  const [open, setOpen] = useState(false);

  const [showProfileForm, setShowProfileForm] = useState(false);
  const [profile, setProfile] = useState({ name: "", email: "" });
  const [profileErr, setProfileErr] = useState(null);
  const [profileOk, setProfileOk] = useState(null);
  const [savingProfile, setSavingProfile] = useState(false);

  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const [pwErr, setPwErr] = useState(null);
  const [pwOk, setPwOk] = useState(null);
  const [photoErr, setPhotoErr] = useState(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const [showAddAdminForm, setShowAddAdminForm] = useState(false);
  const [newAdmin, setNewAdmin] = useState({ name: "", email: "", password: "" });
  const [addAdminErr, setAddAdminErr] = useState(null);
  const [addAdminOk, setAddAdminOk] = useState(null);
  const [savingAdmin, setSavingAdmin] = useState(false);

  const [showResets, setShowResets] = useState(false);
  const [resets, setResets] = useState([]);
  const [resetsErr, setResetsErr] = useState(null);
  const [loadingResets, setLoadingResets] = useState(false);

  const [showBuildings, setShowBuildings] = useState(false);
  const [buildings, setBuildings] = useState([]);
  const [loadingBuildings, setLoadingBuildings] = useState(false);
  const [buildingErr, setBuildingErr] = useState(null);
  const [buildingOk, setBuildingOk] = useState(null);
  const [newBuildingName, setNewBuildingName] = useState("");

  const [showScopes, setShowScopes] = useState(false);
  const [loadingScopes, setLoadingScopes] = useState(false);
  const [scopesErr, setScopesErr] = useState(null);
  const [scopesOk, setScopesOk] = useState(null);
  const [adminScopes, setAdminScopes] = useState([]);
  const [operationalScopes, setOperationalScopes] = useState([]);
  const [adminUsers, setAdminUsers] = useState([]);
  const [scopeFaculties, setScopeFaculties] = useState([]);
  const [scopeDepartments, setScopeDepartments] = useState([]);
  const [scopeBuildings, setScopeBuildings] = useState([]);
  const [showGrantForm, setShowGrantForm] = useState(false);
  const [grantForm, setGrantForm] = useState({
    userId: "", grantType: "academic", facultyId: "", departmentId: "", operationalScopeId: "",
  });
  const [savingGrant, setSavingGrant] = useState(false);
  const [showOpScopeForm, setShowOpScopeForm] = useState(false);
  const [opScopeForm, setOpScopeForm] = useState({ name: "", scopeType: "HVAC", buildingId: "" });
  const [savingOpScope, setSavingOpScope] = useState(false);

  const [showAudit, setShowAudit] = useState(false);
  const [auditRows, setAuditRows] = useState([]);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [auditErr, setAuditErr] = useState(null);
  const [auditExpanded, setAuditExpanded] = useState(null);
  const AUDIT_PAGE_SIZE = 20;
  const [auditOffset, setAuditOffset] = useState(0);
  const [auditHasMore, setAuditHasMore] = useState(false);
  const emptyAuditFilters = { resourceType: "", result: "", q: "", since: "", until: "" };
  const [auditFilters, setAuditFilters] = useState(emptyAuditFilters);
  const AUDIT_RESOURCE_TYPES = [
    "user", "faculty", "department", "course", "admin_scope", "operational_scope",
    "zone", "sensor", "device", "automation_rule", "zone_schedule", "building",
    "system_settings", "password_reset_request", "door",
  ];

  const [showEnergy, setShowEnergy] = useState(false);
  const [checkoutTime, setCheckoutTime] = useState("18:00");
  const [loadingEnergy, setLoadingEnergy] = useState(false);
  const [energyErr, setEnergyErr] = useState(null);
  const [energyOk, setEnergyOk] = useState(null);
  const [savingCheckout, setSavingCheckout] = useState(false);
  const [sweepBusy, setSweepBusy] = useState(false);
  const [sweepResult, setSweepResult] = useState(null);

  async function loadResets() {
    setLoadingResets(true);
    setResetsErr(null);
    try {
      const list = await api.listPasswordResets();
      setResets(list);
    } catch (e) {
      setResetsErr(e instanceof ApiError ? e.message : "Could not load reset requests.");
    } finally {
      setLoadingResets(false);
    }
  }

  function openResets() {
    setShowResets(true);
    loadResets();
  }

  async function handleApproveReset(requestId) {
    setResetsErr(null);
    try {
      // No password is generated here — the user's own browser (already
      // polling with its request_token) picks this up and lets them set
      // their own new password directly.
      await api.approvePasswordReset(requestId);
      await loadResets();
    } catch (e) {
      setResetsErr(e instanceof ApiError ? e.message : "Could not approve this request.");
    }
  }

  async function handleDenyReset(requestId) {
    setResetsErr(null);
    try {
      await api.denyPasswordReset(requestId);
      await loadResets();
    } catch (e) {
      setResetsErr(e instanceof ApiError ? e.message : "Could not deny this request.");
    }
  }

  async function loadBuildingsList() {
    setLoadingBuildings(true);
    setBuildingErr(null);
    try {
      const list = await api.listBuildings();
      setBuildings(list);
    } catch (e) {
      setBuildingErr(e instanceof ApiError ? e.message : "Could not load buildings.");
    } finally {
      setLoadingBuildings(false);
    }
  }

  function openBuildings() {
    setShowBuildings(true);
    setBuildingOk(null);
    loadBuildingsList();
  }

  async function handleAddBuilding(e) {
    e.preventDefault();
    setBuildingErr(null);
    setBuildingOk(null);
    const name = newBuildingName.trim();
    if (!name) {
      setBuildingErr("Enter a building name.");
      return;
    }
    try {
      await api.createBuilding(name);
      setBuildingOk(`Added "${name}".`);
      setNewBuildingName("");
      await loadBuildingsList();
    } catch (e) {
      setBuildingErr(e instanceof ApiError ? e.message : "Could not add building.");
    }
  }

  async function handleRemoveBuilding(buildingId, name) {
    setBuildingErr(null);
    setBuildingOk(null);
    if (!window.confirm(`Remove building "${name}"?`)) return;
    try {
      await api.deleteBuilding(buildingId);
      setBuildingOk(`Removed "${name}".`);
      await loadBuildingsList();
    } catch (e) {
      setBuildingErr(e instanceof ApiError ? e.message : "Could not remove building.");
    }
  }

  async function loadEnergySettings() {
    setLoadingEnergy(true);
    setEnergyErr(null);
    try {
      const settings = await api.getSystemSettings();
      setCheckoutTime(settings.checkout_time);
    } catch (e) {
      setEnergyErr(e instanceof ApiError ? e.message : "Could not load checkout settings.");
    } finally {
      setLoadingEnergy(false);
    }
  }

  function openEnergy() {
    setShowEnergy(true);
    setEnergyOk(null);
    setSweepResult(null);
    loadEnergySettings();
  }

  async function handleSaveCheckoutTime(e) {
    e.preventDefault();
    setEnergyErr(null);
    setEnergyOk(null);
    setSavingCheckout(true);
    try {
      await api.updateSystemSettings(checkoutTime);
      setEnergyOk(`Daily checkout time set to ${checkoutTime}.`);
    } catch (e) {
      setEnergyErr(e instanceof ApiError ? e.message : "Could not save checkout time.");
    } finally {
      setSavingCheckout(false);
    }
  }

  async function handleRunSweep() {
    setEnergyErr(null);
    setSweepBusy(true);
    setSweepResult(null);
    try {
      const result = await api.runCheckoutSweep();
      setSweepResult(result);
    } catch (e) {
      setEnergyErr(e instanceof ApiError ? e.message : "Could not run the checkout sweep.");
    } finally {
      setSweepBusy(false);
    }
  }

  // ---------------------------------------------------------------------
  // Phase 12: AdminScope / OperationalScope management. Only ever rendered
  // for an unrestricted admin (user.is_scope_restricted === false, set by
  // GET /api/users/me — see routers/users.py) since the backend's
  // _require_unrestricted_admin (academic.py) 403s a scoped admin on every
  // one of these endpoints regardless of what the UI shows; hiding it for
  // anyone else avoids a button that would just fail.
  // ---------------------------------------------------------------------
  async function loadScopesData() {
    setLoadingScopes(true);
    setScopesErr(null);
    try {
      const [grants, opScopes, users, faculties, buildings] = await Promise.all([
        api.listAdminScopes(),
        api.listOperationalScopes(),
        api.listUsers(),
        api.listFaculties(),
        api.listBuildings(),
      ]);
      setAdminScopes(grants);
      setOperationalScopes(opScopes);
      setAdminUsers(users.filter((u) => u.role === "admin"));
      setScopeFaculties(faculties);
      setScopeBuildings(buildings);
    } catch (e) {
      setScopesErr(e instanceof ApiError ? e.message : "Could not load scope data.");
    } finally {
      setLoadingScopes(false);
    }
  }

  function openScopes() {
    setShowScopes(true);
    setScopesOk(null);
    loadScopesData();
  }

  async function handleGrantFacultyChange(facultyId) {
    setGrantForm((f) => ({ ...f, facultyId, departmentId: "" }));
    if (!facultyId) {
      setScopeDepartments([]);
      return;
    }
    try {
      const depts = await api.listDepartments(Number(facultyId));
      setScopeDepartments(depts);
    } catch {
      setScopeDepartments([]);
    }
  }

  async function handleCreateGrant(e) {
    e.preventDefault();
    setScopesErr(null);
    setScopesOk(null);
    if (!grantForm.userId) {
      setScopesErr("Choose an admin to grant a scope to.");
      return;
    }
    const payload = { user_id: Number(grantForm.userId) };
    if (grantForm.grantType === "academic") {
      if (!grantForm.facultyId) {
        setScopesErr("Choose a college for an academic scope grant.");
        return;
      }
      payload.faculty_id = Number(grantForm.facultyId);
      if (grantForm.departmentId) payload.department_id = Number(grantForm.departmentId);
    } else {
      if (!grantForm.operationalScopeId) {
        setScopesErr("Choose an operational scope to grant.");
        return;
      }
      payload.operational_scope_id = Number(grantForm.operationalScopeId);
    }
    setSavingGrant(true);
    try {
      await api.createAdminScope(payload);
      setScopesOk("Scope granted.");
      setGrantForm({ userId: "", grantType: "academic", facultyId: "", departmentId: "", operationalScopeId: "" });
      setScopeDepartments([]);
      setShowGrantForm(false);
      await loadScopesData();
    } catch (e) {
      setScopesErr(e instanceof ApiError ? e.message : "Could not grant this scope.");
    } finally {
      setSavingGrant(false);
    }
  }

  async function handleRevokeGrant(scopeId, label) {
    setScopesErr(null);
    setScopesOk(null);
    if (!window.confirm(`Revoke scope grant "${label}"?`)) return;
    try {
      await api.deleteAdminScope(scopeId);
      setScopesOk("Scope revoked.");
      await loadScopesData();
    } catch (e) {
      setScopesErr(e instanceof ApiError ? e.message : "Could not revoke this scope.");
    }
  }

  async function handleClearAllGrantsForUser(userId, label) {
    setScopesErr(null);
    setScopesOk(null);
    const rows = adminScopes.filter((s) => s.user_id === userId);
    if (rows.length === 0) return;
    if (!window.confirm(`Clear all ${rows.length} scope grant(s) for ${label}?`)) return;
    try {
      for (const row of rows) {
        // eslint-disable-next-line no-await-in-loop
        await api.deleteAdminScope(row.scope_id);
      }
      setScopesOk(`Cleared all scopes for ${label}.`);
      await loadScopesData();
    } catch (e) {
      setScopesErr(e instanceof ApiError ? e.message : "Could not clear all scopes — some may have been removed.");
      await loadScopesData();
    }
  }

  async function handleCreateOpScope(e) {
    e.preventDefault();
    setScopesErr(null);
    setScopesOk(null);
    const name = opScopeForm.name.trim();
    if (!name) {
      setScopesErr("Enter a name for the operational scope.");
      return;
    }
    setSavingOpScope(true);
    try {
      await api.createOperationalScope({
        name, scope_type: opScopeForm.scopeType,
        building_id: opScopeForm.buildingId ? Number(opScopeForm.buildingId) : null,
      });
      setScopesOk(`Created operational scope "${name}".`);
      setOpScopeForm({ name: "", scopeType: "HVAC", buildingId: "" });
      setShowOpScopeForm(false);
      await loadScopesData();
    } catch (e) {
      setScopesErr(e instanceof ApiError ? e.message : "Could not create operational scope.");
    } finally {
      setSavingOpScope(false);
    }
  }

  async function handleDeleteOpScope(scopeId, name) {
    setScopesErr(null);
    setScopesOk(null);
    if (!window.confirm(`Delete operational scope "${name}"?`)) return;
    try {
      await api.deleteOperationalScope(scopeId);
      setScopesOk(`Deleted "${name}".`);
      await loadScopesData();
    } catch (e) {
      // e.g. 409 "N admin scope grant(s) still use it" — surfaced verbatim,
      // this is a real backend dependency check, not a UI-only guess.
      setScopesErr(e instanceof ApiError ? e.message : "Could not delete this operational scope.");
    }
  }

  function userLabel(userId) {
    const u = adminUsers.find((x) => x.user_id === userId);
    return u ? `${u.name} (${u.email})` : `User #${userId}`;
  }

  function grantLabel(grant) {
    if (grant.operational_scope_id) return grant.operational_scope_name || `Operational scope #${grant.operational_scope_id}`;
    if (grant.department_id) return `${grant.faculty_name || "College"} / ${grant.department_name || "Dept"}`;
    return grant.faculty_name || `College #${grant.faculty_id}`;
  }

  // ---------------------------------------------------------------------
  // Master UX pass: real Audit Log viewer. Backend is unrestricted-admin-
  // only (routers/audit_logs.py::_require_unrestricted_admin) and read-only
  // (no PUT/PATCH/DELETE) by design — this panel never claims otherwise.
  // Filters map 1:1 to real query params the backend actually supports
  // (resource_type, result, actor_user_id, q, since, until, limit, offset —
  // the last four added this pass); nothing here is filtered client-side
  // against a bigger hidden fetch.
  // ---------------------------------------------------------------------
  function activeAuditFilterCount() {
    return Object.values(auditFilters).filter((v) => v).length;
  }

  async function loadAudit(offset = 0) {
    setLoadingAudit(true);
    setAuditErr(null);
    try {
      const params = {
        resource_type: auditFilters.resourceType || undefined,
        result: auditFilters.result || undefined,
        q: auditFilters.q || undefined,
        since: auditFilters.since || undefined,
        until: auditFilters.until || undefined,
        limit: AUDIT_PAGE_SIZE,
        offset,
      };
      const rows = await api.listAuditLogs(params);
      setAuditRows(rows);
      setAuditOffset(offset);
      // We don't get a total count back — a real "is there more" signal
      // (fetching PAGE_SIZE+1 would work, but changes what limit means) is a
      // fair trade for exact totals here: a full page suggests another page
      // may exist, which is what enables/disables "Next" below.
      setAuditHasMore(rows.length === AUDIT_PAGE_SIZE);
    } catch (e) {
      setAuditErr(e instanceof ApiError ? e.message : "Could not load the audit log.");
    } finally {
      setLoadingAudit(false);
    }
  }

  function openAudit() {
    setShowAudit(true);
    setAuditFilters(emptyAuditFilters);
    setAuditExpanded(null);
    loadAudit(0);
  }

  function applyAuditFilters(e) {
    e.preventDefault();
    loadAudit(0);
  }

  function clearAuditFilters() {
    setAuditFilters(emptyAuditFilters);
    loadAudit(0);
  }

  // A short, human-readable line built from the structured fields — the raw
  // action/resource_type/resource_id/result stay visible underneath in the
  // "Technical details" toggle, this is purely a presentation layer on top
  // of real fields, never invented data.
  function describeAuditRow(r) {
    const who = r.actor_email || "System";
    const what = r.resource_label || `${r.resource_type} #${r.resource_id ?? "?"}`;
    const verb = { create: "created", update: "updated", delete: "deleted", grant: "granted", revoke: "revoked",
      approve: "approved", deny: "denied", login_failed: "failed to log in as", login_success: "logged in as" }[r.action] || r.action;
    if (r.action === "login_success" || r.action === "login_failed") return `${who} ${verb}`;
    return `${who} ${verb} ${r.resource_type.replace(/_/g, " ")} "${what}"`;
  }

  async function handleAddAdmin(e) {
    e.preventDefault();
    setAddAdminErr(null);
    setAddAdminOk(null);
    if (!newAdmin.name.trim() || !newAdmin.email.trim() || !newAdmin.password) {
      setAddAdminErr("Name, email, and password are all required.");
      return;
    }
    setSavingAdmin(true);
    try {
      const created = await api.createUser({
        name: newAdmin.name.trim(),
        email: newAdmin.email.trim(),
        role: "admin",
        password: newAdmin.password,
      });
      setAddAdminOk(`Added admin ${created.name} (${created.email}). Give them this email + the password you set.`);
      setNewAdmin({ name: "", email: "", password: "" });
      setShowAddAdminForm(false);
    } catch (e) {
      setAddAdminErr(e instanceof ApiError ? e.message : "Could not create admin account.");
    } finally {
      setSavingAdmin(false);
    }
  }

  function openProfileForm() {
    setProfile({ name: user?.name || "", email: user?.email || "" });
    setProfileErr(null);
    setProfileOk(null);
    setShowProfileForm(true);
  }

  async function handleSaveProfile(e) {
    e.preventDefault();
    setProfileErr(null);
    setProfileOk(null);
    if (!profile.name.trim() || !profile.email.trim()) {
      setProfileErr("Name and email can't be empty.");
      return;
    }
    setSavingProfile(true);
    try {
      await api.updateProfile({ name: profile.name.trim(), email: profile.email.trim() });
    } catch (e) {
      setProfileErr(e instanceof ApiError ? e.message : "Could not update profile.");
      setSavingProfile(false);
      return;
    }
    try {
      // Email is the JWT subject — refresh the token so it matches the new
      // email, or the very next request would 401.
      const { access_token } = await api.refreshToken();
      setToken(access_token);
      await refreshProfile();
      setProfileOk("Profile updated.");
      setShowProfileForm(false);
    } catch (e) {
      // The profile change itself already succeeded here — only the token
      // refresh failed. A 401 on this call already triggers AuthContext's
      // onUnauthorized() -> logout(), sending the user back to the login
      // screen, so don't also claim the update failed.
      setProfileErr(
        e instanceof ApiError && e.status === 401
          ? "Profile saved. Please sign in again to continue."
          : e instanceof ApiError
            ? e.message
            : "Profile saved, but your session could not be refreshed."
      );
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleChangePassword(e) {
    e.preventDefault();
    setPwErr(null);
    setPwOk(null);
    if (!pw.current || !pw.next) {
      setPwErr("Fill in both your current and new password.");
      return;
    }
    if (pw.next !== pw.confirm) {
      setPwErr("New password and confirmation don't match.");
      return;
    }
    try {
      await api.changePassword(pw.current, pw.next);
      setPwOk("Password updated.");
      setPw({ current: "", next: "", confirm: "" });
      setShowPasswordForm(false);
    } catch (e) {
      setPwErr(e instanceof ApiError ? e.message : "Could not change password.");
    }
  }

  async function handlePhotoChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhotoErr(null);
    setUploading(true);
    try {
      await api.uploadPhoto(file);
      await refreshProfile();
    } catch (e) {
      setPhotoErr(e instanceof ApiError ? e.message : "Could not upload photo.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const avatarSrc = mediaUrl(user?.photo_url);

  return (
    <div className="account-menu">
      <button
        type="button"
        className="account-avatar-btn"
        onClick={() => setOpen((o) => !o)}
        title="Account"
      >
        {avatarSrc ? (
          <img src={avatarSrc} alt="" className="account-avatar-img" />
        ) : (
          <span className="account-avatar-fallback">{initialsOf(user?.name || user?.email)}</span>
        )}
      </button>

      {open && (
        <div className="account-dropdown">
          <div className="account-dropdown-header">
            <strong>{user?.name || user?.email}</strong>
            <span className="muted">{user?.email} ({user?.role})</span>
          </div>

          <label className="account-dropdown-action">
            {uploading ? "Uploading…" : "Change photo"}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              onChange={handlePhotoChange}
              disabled={uploading}
              style={{ display: "none" }}
            />
          </label>
          {photoErr && <div className="form-error">{photoErr}</div>}

          {!showProfileForm ? (
            <button type="button" className="account-dropdown-action" onClick={openProfileForm}>
              Edit name / email
            </button>
          ) : (
            <form onSubmit={handleSaveProfile} className="account-password-form">
              <input
                placeholder="Full name"
                value={profile.name}
                onChange={(e) => setProfile({ ...profile, name: e.target.value })}
              />
              <input
                type="email"
                placeholder="Email"
                value={profile.email}
                onChange={(e) => setProfile({ ...profile, email: e.target.value })}
              />
              {profileErr && <div className="form-error">{profileErr}</div>}
              <div style={{ display: "flex", gap: "8px" }}>
                <button type="submit" disabled={savingProfile}>
                  {savingProfile ? "Saving…" : "Save"}
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => { setShowProfileForm(false); setProfileErr(null); }}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
          {profileOk && <div className="form-success">{profileOk}</div>}

          {!showPasswordForm ? (
            <button
              type="button"
              className="account-dropdown-action"
              onClick={() => { setShowPasswordForm(true); setPwOk(null); }}
            >
              Change password
            </button>
          ) : (
            <form onSubmit={handleChangePassword} className="account-password-form">
              <input
                type="password"
                placeholder="Current password"
                value={pw.current}
                onChange={(e) => setPw({ ...pw, current: e.target.value })}
              />
              <input
                type="password"
                placeholder="New password"
                value={pw.next}
                onChange={(e) => setPw({ ...pw, next: e.target.value })}
              />
              <input
                type="password"
                placeholder="Confirm new password"
                value={pw.confirm}
                onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
              />
              {pwErr && <div className="form-error">{pwErr}</div>}
              <div style={{ display: "flex", gap: "8px" }}>
                <button type="submit">Save</button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => { setShowPasswordForm(false); setPwErr(null); }}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
          {pwOk && <div className="form-success">{pwOk}</div>}

          {user?.role === "admin" && (
            <>
              <div style={{ borderTop: "1px solid var(--border)", margin: "8px 0" }} />

              {!showResets ? (
                <button type="button" className="account-dropdown-action" onClick={openResets}>
                  Password reset requests
                </button>
              ) : (
                <div className="account-password-form">
                  {loadingResets && <p className="muted" style={{ margin: 0 }}>Loading…</p>}
                  {resetsErr && <div className="form-error">{resetsErr}</div>}
                  {!loadingResets && resets.length === 0 && (
                    <p className="muted" style={{ margin: 0 }}>No pending requests.</p>
                  )}
                  {resets.map((r) => (
                    <div
                      key={r.request_id}
                      style={{ borderBottom: "1px solid var(--border)", paddingBottom: "8px" }}
                    >
                      <strong style={{ fontSize: "13px" }}>{r.user_name || r.user_email}</strong>
                      <div className="muted" style={{ fontSize: "12px" }}>{r.user_email}</div>
                      <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
                        <button type="button" onClick={() => handleApproveReset(r.request_id)}>
                          Approve
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => handleDenyReset(r.request_id)}
                        >
                          Deny
                        </button>
                      </div>
                    </div>
                  ))}
                  <button type="button" className="secondary" onClick={() => setShowResets(false)}>
                    Close
                  </button>
                </div>
              )}

              <div style={{ borderTop: "1px solid var(--border)", margin: "8px 0" }} />

              {!showBuildings ? (
                <button type="button" className="account-dropdown-action" onClick={openBuildings}>
                  Manage buildings
                </button>
              ) : (
                <div className="account-password-form">
                  {loadingBuildings && <p className="muted" style={{ margin: 0 }}>Loading…</p>}
                  <ul style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: "160px", overflowY: "auto" }}>
                    {buildings.map((b) => (
                      <li
                        key={b.building_id}
                        style={{
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                          padding: "6px 0", borderBottom: "1px solid var(--border)", fontSize: "13px",
                        }}
                      >
                        <span>{b.name}</span>
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => handleRemoveBuilding(b.building_id, b.name)}
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                    {!loadingBuildings && buildings.length === 0 && (
                      <li className="muted" style={{ padding: "4px 0" }}>No buildings yet.</li>
                    )}
                  </ul>
                  <form onSubmit={handleAddBuilding} style={{ display: "flex", gap: "6px" }}>
                    <input
                      placeholder="New building name"
                      value={newBuildingName}
                      onChange={(e) => setNewBuildingName(e.target.value)}
                      style={{ flex: 1 }}
                    />
                    <button type="submit">Add</button>
                  </form>
                  {buildingErr && <div className="form-error">{buildingErr}</div>}
                  {buildingOk && <div className="form-success">{buildingOk}</div>}
                  <button type="button" className="secondary" onClick={() => setShowBuildings(false)}>
                    Close
                  </button>
                </div>
              )}

              {user?.is_scope_restricted === false && (
                <>
                  <div style={{ borderTop: "1px solid var(--border)", margin: "8px 0" }} />

                  {!showAudit ? (
                    <button type="button" className="account-dropdown-action" onClick={openAudit}>
                      Audit log
                    </button>
                  ) : (
                    <div className="account-password-form" style={{ minWidth: 320 }}>
                      <form onSubmit={applyAuditFilters} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          <select
                            value={auditFilters.resourceType}
                            onChange={(e) => setAuditFilters({ ...auditFilters, resourceType: e.target.value })}
                            style={{ flex: 1, minWidth: 140 }}
                          >
                            <option value="">All resource types</option>
                            {AUDIT_RESOURCE_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
                          </select>
                          <select
                            value={auditFilters.result}
                            onChange={(e) => setAuditFilters({ ...auditFilters, result: e.target.value })}
                          >
                            <option value="">Any result</option>
                            <option value="success">Success</option>
                            <option value="failure">Failure</option>
                          </select>
                        </div>
                        <input
                          placeholder="Search label/description…"
                          value={auditFilters.q}
                          onChange={(e) => setAuditFilters({ ...auditFilters, q: e.target.value })}
                        />
                        <div style={{ display: "flex", gap: 6 }}>
                          <label className="muted" style={{ fontSize: 11, display: "flex", flexDirection: "column", flex: 1 }}>
                            Since
                            <input type="date" value={auditFilters.since} onChange={(e) => setAuditFilters({ ...auditFilters, since: e.target.value })} />
                          </label>
                          <label className="muted" style={{ fontSize: 11, display: "flex", flexDirection: "column", flex: 1 }}>
                            Until
                            <input type="date" value={auditFilters.until} onChange={(e) => setAuditFilters({ ...auditFilters, until: e.target.value })} />
                          </label>
                        </div>
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                          <button type="submit" disabled={loadingAudit}>{loadingAudit ? "Loading…" : "Apply filters"}</button>
                          <button type="button" className="secondary" onClick={clearAuditFilters} disabled={loadingAudit}>
                            Clear filters{activeAuditFilterCount() > 0 ? ` (${activeAuditFilterCount()})` : ""}
                          </button>
                        </div>
                      </form>

                      {auditErr && <div className="form-error">{auditErr}</div>}
                      {loadingAudit && <p className="muted" style={{ margin: 0 }}>Loading…</p>}

                      {!loadingAudit && auditRows.length === 0 && !auditErr && (
                        <p className="muted" style={{ margin: 0 }}>No audit entries match these filters.</p>
                      )}

                      <ul style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: 260, overflowY: "auto" }}>
                        {auditRows.map((r) => (
                          <li key={r.log_id} style={{ borderBottom: "1px solid var(--border)", padding: "6px 0" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", gap: 6, alignItems: "baseline" }}>
                              <span style={{ fontSize: 12 }}>{describeAuditRow(r)}</span>
                              <span className={`aa-status-pill ${r.result === "failure" ? "expired" : "active"}`} style={{ fontSize: 10 }}>
                                {r.result}
                              </span>
                            </div>
                            <div className="muted" style={{ fontSize: 11 }}>
                              {new Date(r.timestamp + "Z").toLocaleString()} (local time; stored UTC)
                            </div>
                            <button
                              type="button"
                              className="link-button"
                              style={{ fontSize: 11 }}
                              onClick={() => setAuditExpanded(auditExpanded === r.log_id ? null : r.log_id)}
                            >
                              {auditExpanded === r.log_id ? "Hide technical details" : "Technical details"}
                            </button>
                            {auditExpanded === r.log_id && (
                              <dl className="aa-profile-grid" style={{ fontSize: 11, marginTop: 4 }}>
                                <div><dt>Action</dt><dd>{r.action}</dd></div>
                                <div><dt>Resource type</dt><dd>{r.resource_type}</dd></div>
                                <div><dt>Resource ID</dt><dd>{r.resource_id ?? "—"}</dd></div>
                                <div><dt>Actor role</dt><dd>{r.actor_role || "—"}</dd></div>
                                <div><dt>Description</dt><dd>{r.description || "—"}</dd></div>
                              </dl>
                            )}
                          </li>
                        ))}
                      </ul>

                      <div style={{ display: "flex", gap: 8, justifyContent: "space-between" }}>
                        <button type="button" className="secondary" disabled={loadingAudit || auditOffset === 0}
                                onClick={() => loadAudit(Math.max(0, auditOffset - AUDIT_PAGE_SIZE))}>
                          &larr; Newer
                        </button>
                        <button type="button" className="secondary" disabled={loadingAudit || !auditHasMore}
                                onClick={() => loadAudit(auditOffset + AUDIT_PAGE_SIZE)}>
                          Older &rarr;
                        </button>
                      </div>
                      <p className="muted" style={{ fontSize: 10, margin: 0 }}>
                        Read-only, unrestricted-admin-only by design. Covers admin/security mutations only —
                        automation/MQTT-triggered actions are recorded separately in the Smart Building automation log.
                      </p>
                      <button type="button" className="secondary" onClick={() => setShowAudit(false)}>Close</button>
                    </div>
                  )}

                  <div style={{ borderTop: "1px solid var(--border)", margin: "8px 0" }} />

                  {!showScopes ? (
                    <button type="button" className="account-dropdown-action" onClick={openScopes}>
                      Manage admin scopes
                    </button>
                  ) : (
                    <div className="account-password-form">
                      {loadingScopes && <p className="muted" style={{ margin: 0 }}>Loading…</p>}

                      <strong style={{ fontSize: "13px" }}>Academic / operational grants</strong>
                      <ul style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: "180px", overflowY: "auto" }}>
                        {adminScopes.map((s) => (
                          <li
                            key={s.scope_id}
                            style={{
                              display: "flex", alignItems: "center", justifyContent: "space-between",
                              padding: "6px 0", borderBottom: "1px solid var(--border)", fontSize: "13px", gap: "6px",
                            }}
                          >
                            <span>
                              <strong>{userLabel(s.user_id)}</strong>
                              <div className="muted" style={{ fontSize: "12px" }}>{grantLabel(s)}</div>
                            </span>
                            <button
                              type="button"
                              className="link-button"
                              onClick={() => handleRevokeGrant(s.scope_id, grantLabel(s))}
                            >
                              Revoke
                            </button>
                          </li>
                        ))}
                        {!loadingScopes && adminScopes.length === 0 && (
                          <li className="muted" style={{ padding: "4px 0" }}>No scope grants yet — every admin is unrestricted.</li>
                        )}
                      </ul>

                      {adminUsers.length > 0 && (
                        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                          {[...new Set(adminScopes.map((s) => s.user_id))].map((uid) => (
                            <button
                              key={uid}
                              type="button"
                              className="link-button"
                              style={{ fontSize: "11px" }}
                              onClick={() => handleClearAllGrantsForUser(uid, userLabel(uid))}
                            >
                              Clear all for {userLabel(uid)}
                            </button>
                          ))}
                        </div>
                      )}

                      {!showGrantForm ? (
                        <button type="button" onClick={() => setShowGrantForm(true)}>+ Grant a scope</button>
                      ) : (
                        <form onSubmit={handleCreateGrant} style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                          <select
                            value={grantForm.userId}
                            onChange={(e) => setGrantForm({ ...grantForm, userId: e.target.value })}
                          >
                            <option value="">Select admin…</option>
                            {adminUsers.map((u) => (
                              <option key={u.user_id} value={u.user_id}>{u.name} ({u.email})</option>
                            ))}
                          </select>
                          <select
                            value={grantForm.grantType}
                            onChange={(e) => setGrantForm({ ...grantForm, grantType: e.target.value, facultyId: "", departmentId: "", operationalScopeId: "" })}
                          >
                            <option value="academic">College / Department</option>
                            <option value="operational">Operational scope</option>
                          </select>
                          {grantForm.grantType === "academic" ? (
                            <>
                              <select
                                value={grantForm.facultyId}
                                onChange={(e) => handleGrantFacultyChange(e.target.value)}
                              >
                                <option value="">Select college…</option>
                                {scopeFaculties.map((f) => (
                                  <option key={f.faculty_id} value={f.faculty_id}>{f.name}</option>
                                ))}
                              </select>
                              <select
                                value={grantForm.departmentId}
                                onChange={(e) => setGrantForm({ ...grantForm, departmentId: e.target.value })}
                                disabled={!grantForm.facultyId}
                              >
                                <option value="">Whole college (all departments)</option>
                                {scopeDepartments.map((d) => (
                                  <option key={d.department_id} value={d.department_id}>{d.name}</option>
                                ))}
                              </select>
                            </>
                          ) : (
                            <select
                              value={grantForm.operationalScopeId}
                              onChange={(e) => setGrantForm({ ...grantForm, operationalScopeId: e.target.value })}
                            >
                              <option value="">Select operational scope…</option>
                              {operationalScopes.map((s) => (
                                <option key={s.scope_id} value={s.scope_id}>{s.name} ({s.scope_type})</option>
                              ))}
                            </select>
                          )}
                          <div style={{ display: "flex", gap: "8px" }}>
                            <button type="submit" disabled={savingGrant}>{savingGrant ? "Saving…" : "Grant"}</button>
                            <button type="button" className="secondary" onClick={() => setShowGrantForm(false)}>Cancel</button>
                          </div>
                        </form>
                      )}

                      <div style={{ borderTop: "1px solid var(--border)", margin: "6px 0" }} />
                      <strong style={{ fontSize: "13px" }}>Operational scopes</strong>
                      <ul style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: "140px", overflowY: "auto" }}>
                        {operationalScopes.map((s) => (
                          <li
                            key={s.scope_id}
                            style={{
                              display: "flex", alignItems: "center", justifyContent: "space-between",
                              padding: "6px 0", borderBottom: "1px solid var(--border)", fontSize: "13px",
                            }}
                          >
                            <span>{s.name} <span className="muted">({s.scope_type}{s.building_name ? ` — ${s.building_name}` : ""})</span></span>
                            <button type="button" className="link-button" onClick={() => handleDeleteOpScope(s.scope_id, s.name)}>
                              Delete
                            </button>
                          </li>
                        ))}
                        {!loadingScopes && operationalScopes.length === 0 && (
                          <li className="muted" style={{ padding: "4px 0" }}>No operational scopes yet.</li>
                        )}
                      </ul>

                      {!showOpScopeForm ? (
                        <button type="button" onClick={() => setShowOpScopeForm(true)}>+ New operational scope</button>
                      ) : (
                        <form onSubmit={handleCreateOpScope} style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                          <input
                            placeholder="Name (e.g. HVAC — North Campus)"
                            value={opScopeForm.name}
                            onChange={(e) => setOpScopeForm({ ...opScopeForm, name: e.target.value })}
                          />
                          <select
                            value={opScopeForm.scopeType}
                            onChange={(e) => setOpScopeForm({ ...opScopeForm, scopeType: e.target.value })}
                          >
                            {["HVAC", "ELECTRICAL", "RESIDENTIAL", "ADMINISTRATIVE", "ENGINEERING"].map((t) => (
                              <option key={t} value={t}>{t}</option>
                            ))}
                          </select>
                          <select
                            value={opScopeForm.buildingId}
                            onChange={(e) => setOpScopeForm({ ...opScopeForm, buildingId: e.target.value })}
                          >
                            <option value="">No specific building</option>
                            {scopeBuildings.map((b) => (
                              <option key={b.building_id} value={b.building_id}>{b.name}</option>
                            ))}
                          </select>
                          <div style={{ display: "flex", gap: "8px" }}>
                            <button type="submit" disabled={savingOpScope}>{savingOpScope ? "Saving…" : "Create"}</button>
                            <button type="button" className="secondary" onClick={() => setShowOpScopeForm(false)}>Cancel</button>
                          </div>
                        </form>
                      )}

                      {scopesErr && <div className="form-error">{scopesErr}</div>}
                      {scopesOk && <div className="form-success">{scopesOk}</div>}
                      <button type="button" className="secondary" onClick={() => setShowScopes(false)}>Close</button>
                    </div>
                  )}
                </>
              )}

              <div style={{ borderTop: "1px solid var(--border)", margin: "8px 0" }} />

              {!showEnergy ? (
                <button type="button" className="account-dropdown-action" onClick={openEnergy}>
                  Energy &amp; checkout
                </button>
              ) : (
                <div className="account-password-form">
                  {loadingEnergy && <p className="muted" style={{ margin: 0 }}>Loading…</p>}
                  <form onSubmit={handleSaveCheckoutTime} style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                    <label className="muted" style={{ fontSize: "12px" }}>Daily checkout time</label>
                    <input
                      type="time"
                      value={checkoutTime}
                      onChange={(e) => setCheckoutTime(e.target.value)}
                      style={{ flex: 1 }}
                    />
                    <button type="submit" disabled={savingCheckout}>
                      {savingCheckout ? "Saving…" : "Save"}
                    </button>
                  </form>
                  <p className="muted" style={{ fontSize: "12px", margin: "4px 0 0" }}>
                    At this time each day, every room's AC, light, and plugs are
                    switched off automatically, with a final reading logged first.
                  </p>

                  <button type="button" disabled={sweepBusy} onClick={handleRunSweep}>
                    {sweepBusy ? "Running…" : "Run checkout sweep now"}
                  </button>
                  {sweepResult && (
                    <p className="form-success" style={{ margin: 0 }}>
                      {sweepResult.rooms_swept === 0
                        ? "Nothing was on — no rooms needed shutting down."
                        : `Swept ${sweepResult.rooms_swept} room(s): ${sweepResult.door_codes.join(", ")}.`}
                    </p>
                  )}

                  {energyErr && <div className="form-error">{energyErr}</div>}
                  {energyOk && <div className="form-success">{energyOk}</div>}
                  <button type="button" className="secondary" onClick={() => setShowEnergy(false)}>
                    Close
                  </button>
                </div>
              )}

              <div style={{ borderTop: "1px solid var(--border)", margin: "8px 0" }} />

              {!showAddAdminForm ? (
                <button
                  type="button"
                  className="account-dropdown-action"
                  onClick={() => { setShowAddAdminForm(true); setAddAdminOk(null); }}
                >
                  + Add admin
                </button>
              ) : (
                <form onSubmit={handleAddAdmin} className="account-password-form">
                  <input
                    placeholder="Full name"
                    value={newAdmin.name}
                    onChange={(e) => setNewAdmin({ ...newAdmin, name: e.target.value })}
                  />
                  <input
                    type="email"
                    placeholder="Email"
                    value={newAdmin.email}
                    onChange={(e) => setNewAdmin({ ...newAdmin, email: e.target.value })}
                  />
                  <input
                    type="text"
                    placeholder="Password (they'll use this to sign in)"
                    value={newAdmin.password}
                    onChange={(e) => setNewAdmin({ ...newAdmin, password: e.target.value })}
                  />
                  {addAdminErr && <div className="form-error">{addAdminErr}</div>}
                  <div style={{ display: "flex", gap: "8px" }}>
                    <button type="submit" disabled={savingAdmin}>
                      {savingAdmin ? "Saving…" : "Save"}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => { setShowAddAdminForm(false); setAddAdminErr(null); }}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
              {addAdminOk && <div className="form-success">{addAdminOk}</div>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
