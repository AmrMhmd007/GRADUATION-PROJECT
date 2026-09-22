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
      // Email is the JWT subject — refresh the token so it matches the new
      // email, or the very next request would 401.
      const { access_token } = await api.refreshToken();
      setToken(access_token);
      await refreshProfile();
      setProfileOk("Profile updated.");
      setShowProfileForm(false);
    } catch (e) {
      setProfileErr(e instanceof ApiError ? e.message : "Could not update profile.");
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
