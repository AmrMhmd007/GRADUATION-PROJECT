import { useState } from "react";
import { useAuth } from "../AuthContext";
import { api, ApiError } from "../api/client";

// Shown instead of the dashboard whenever the logged-in user still has
// must_change_password set — i.e. an admin just approved a password-reset
// request for them. Blocks access until they replace the admin-issued temp
// password with one only they know.
export default function ForcePasswordChange() {
  const { user, logout, refreshProfile } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setErr(null);
    if (!current || !next) {
      setErr("Enter your temporary password and a new one.");
      return;
    }
    if (next !== confirm) {
      setErr("New password and confirmation don't match.");
      return;
    }
    if (next.length < 6) {
      setErr("New password must be at least 6 characters.");
      return;
    }
    setSubmitting(true);
    try {
      await api.changePassword(current, next);
      await refreshProfile(); // picks up must_change_password: false, so Gate switches to the dashboard
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not change password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <img src="/aiu-logo.png" alt="AIU — Alamein International University" className="login-logo" />
        <h1>Set a new password</h1>
        <p className="subtitle">
          An admin reset your password{user?.name ? `, ${user.name}` : ""}. Pick one only you know to continue.
        </p>

        <label>
          Temporary password
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </label>
        <label>
          New password
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
          />
        </label>
        <label>
          Confirm new password
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
        </label>

        {err && <div className="form-error">{err}</div>}

        <button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : "Save and continue"}
        </button>
        <button type="button" className="link-button" onClick={logout}>
          Sign out instead
        </button>
      </form>
    </div>
  );
}
