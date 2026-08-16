import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { api, getToken, setToken } from "./api/client";

function decodeJwtRole(token) {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return { email: payload.sub, role: payload.role };
  } catch {
    return null;
  }
}

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const token = getToken();
    return token ? decodeJwtRole(token) : null;
  });
  const [error, setError] = useState(null);

  // Enrich the JWT-decoded {email, role} with the full profile (user_id,
  // photo_url, faculty, ...) once we can reach the API — needed for the
  // account menu (avatar, password change).
  const refreshProfile = useCallback(async () => {
    try {
      const me = await api.getMe();
      setUser((prev) => ({ ...prev, ...me }));
    } catch {
      // Token might be stale/invalid — leave the JWT-decoded fallback in
      // place rather than wiping the user out from under an active session.
    }
  }, []);

  useEffect(() => {
    if (getToken()) refreshProfile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email, password) => {
    setError(null);
    try {
      const { access_token } = await api.login(email, password);
      setToken(access_token);
      setUser(decodeJwtRole(access_token));
      await refreshProfile();
      return true;
    } catch (e) {
      setError(e.message || "Login failed");
      return false;
    }
  }, [refreshProfile]);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, logout, error, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
