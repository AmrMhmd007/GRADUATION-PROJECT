import { useEffect, useRef, useState } from "react";
import { useAuth } from "../AuthContext";
import { api, ApiError } from "../api/client";

const STORAGE_KEY = "pwReset";
const POLL_MS = 3000;

// Forgot-password mini flow, all inline on the login card:
//   idle -> form -> waiting -> set-new -> (auto signs in)
// "blocked" is a dead end (denied by an admin, or the link was already
// used) that just sends them back to "idle".
export default function Login() {
  const { login, error } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [stage, setStage] = useState("idle");
  const [forgotEmail, setForgotEmail] = useState("");
  const [token, setToken] = useState(null);
  const [forgotErr, setForgotErr] = useState(null);
  const [sending, setSending] = useState(false);
  const [blockedMessage, setBlockedMessage] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [settingPw, setSettingPw] = useState(false);
  const pollRef = useRef(null);

  // Resume an in-flight request if this tab still has one saved — e.g. the
  // page got reloaded while sitting on the waiting screen.
  useEffect(() => {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (!saved) return;
    try {
      const { token: t, email: e, stage: s } = JSON.parse(saved);
      if (t && (s === "waiting" || s === "set-new")) {
        setToken(t);
        setForgotEmail(e || "");
        setStage(s);
      }
    } catch {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  // Polls for the admin's decision while on the waiting screen. Moves
  // straight to "set-new" the moment it sees "approved" — that's the
  // redirect to the password-change step the user is waiting on.
  useEffect(() => {
    if (stage !== "waiting" || !token) return undefined;

    async function poll() {
      try {
        const { status: s } = await api.checkPasswordResetStatus(token);
        if (s === "approved") {
          setStage("set-new");
          sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ token, email: forgotEmail, stage: "set-new" }));
        } else if (s === "denied") {
          setBlockedMessage("An admin denied this password reset request.");
          setStage("blocked");
          sessionStorage.removeItem(STORAGE_KEY);
        } else if (s === "used") {
          setBlockedMessage("This reset link was already used — start a new request if you still need one.");
          setStage("blocked");
          sessionStorage.removeItem(STORAGE_KEY);
        }
      } catch {
        // Transient network hiccup — just try again on the next tick.
      }
    }

    poll();
    pollRef.current = setInterval(poll, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [stage, token, forgotEmail]);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    await login(email, password);
    setSubmitting(false);
  }

  function openForgot() {
    setStage("form");
    setForgotEmail(email);
    setForgotErr(null);
  }

  function cancelForgot() {
    sessionStorage.removeItem(STORAGE_KEY);
    setStage("idle");
    setForgotErr(null);
    setToken(null);
    setNewPw("");
    setConfirmPw("");
  }

  async function handleForgotSubmit(e) {
    e.preventDefault();
    setForgotErr(null);
    if (!forgotEmail.trim()) {
      setForgotErr("Enter your email first.");
      return;
    }
    setSending(true);
    try {
      const { request_token } = await api.forgotPassword(forgotEmail.trim());
      setToken(request_token);
      setStage("waiting");
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ token: request_token, email: forgotEmail.trim(), stage: "waiting" })
      );
    } catch (e) {
      setForgotErr(e instanceof ApiError ? e.message : "Could not send the request.");
    } finally {
      setSending(false);
    }
  }

  async function handleSetNewPassword(e) {
    e.preventDefault();
    setForgotErr(null);
    if (!newPw) {
      setForgotErr("Enter a new password.");
      return;
    }
    if (newPw !== confirmPw) {
      setForgotErr("New password and confirmation don't match.");
      return;
    }
    if (newPw.length < 6) {
      setForgotErr("New password must be at least 6 characters.");
      return;
    }
    setSettingPw(true);
    try {
      await api.resetPassword(token, newPw);
      sessionStorage.removeItem(STORAGE_KEY);
      await login(forgotEmail, newPw); // signs them straight into the dashboard
    } catch (e) {
      setForgotErr(e instanceof ApiError ? e.message : "Could not set your new password.");
    } finally {
      setSettingPw(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={stage === "idle" ? handleSubmit : (e) => e.preventDefault()}>
        <img src="/aiu-logo.png" alt="AIU — Alamein International University" className="login-logo" />
        <h1>Smart Access Control</h1>
        <p className="subtitle">Secure. Smart. Connected.</p>

        {stage === "idle" && (
          <>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>

            {error && <div className="form-error">{error}</div>}

            <button type="submit" disabled={submitting}>
              {submitting ? "Signing in..." : "Sign in"}
            </button>

            <button type="button" className="link-button" onClick={openForgot}>
              Forgot password?
            </button>
          </>
        )}

        {stage === "form" && (
          <div style={{ marginTop: "4px" }}>
            <p className="hint" style={{ margin: "0 0 6px" }}>
              No email is sent — an admin reviews your request in the dashboard. Keep this tab open; once they
              approve it you'll be able to pick a new password right here.
            </p>
            <input
              type="email"
              placeholder="Your email"
              value={forgotEmail}
              onChange={(e) => setForgotEmail(e.target.value)}
            />
            {forgotErr && <div className="form-error" style={{ marginTop: "8px" }}>{forgotErr}</div>}
            <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
              <button type="button" onClick={handleForgotSubmit} disabled={sending} style={{ margin: 0 }}>
                {sending ? "Sending…" : "Send request"}
              </button>
              <button
                type="button"
                className="secondary"
                style={{ margin: 0, width: "auto" }}
                onClick={cancelForgot}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {stage === "waiting" && (
          <div style={{ marginTop: "4px" }}>
            <p style={{ margin: "0 0 6px", fontSize: "13px" }}>
              Waiting for an admin to approve your request for <strong>{forgotEmail}</strong>…
            </p>
            <p className="hint" style={{ margin: "0 0 10px" }}>
              Keep this tab open — you'll be moved to setting a new password automatically once it's approved.
            </p>
            <button type="button" className="link-button" onClick={cancelForgot}>
              Cancel
            </button>
          </div>
        )}

        {stage === "blocked" && (
          <div style={{ marginTop: "4px" }}>
            <div className="form-error">{blockedMessage}</div>
            <button type="button" className="link-button" onClick={cancelForgot}>
              Back to sign in
            </button>
          </div>
        )}

        {stage === "set-new" && (
          <div style={{ marginTop: "4px" }}>
            <p className="form-success" style={{ marginBottom: "10px" }}>
              Approved — pick a new password for <strong>{forgotEmail}</strong>.
            </p>
            <label>
              New password
              <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
            </label>
            <label>
              Confirm new password
              <input type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} />
            </label>
            {forgotErr && <div className="form-error">{forgotErr}</div>}
            <button type="button" onClick={handleSetNewPassword} disabled={settingPw}>
              {settingPw ? "Saving…" : "Save and sign in"}
            </button>
          </div>
        )}
      </form>
    </div>
  );
}
