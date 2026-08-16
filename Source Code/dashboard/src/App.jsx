import { AuthProvider, useAuth } from "./AuthContext";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import "./App.css";

function Gate() {
  const { user } = useAuth();
  return user ? <Dashboard /> : <Login />;
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
