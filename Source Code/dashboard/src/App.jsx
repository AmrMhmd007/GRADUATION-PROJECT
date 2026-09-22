import { AuthProvider, useAuth } from "./AuthContext";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import ForcePasswordChange from "./pages/ForcePasswordChange";
import "./App.css";

function Gate() {
  const { user } = useAuth();
  if (!user) return <Login />;
  // Set when an admin approves a password-reset request for this account —
  // blocks the dashboard until they replace the admin-issued temp password.
  if (user.must_change_password) return <ForcePasswordChange />;
  return <Dashboard />;
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
