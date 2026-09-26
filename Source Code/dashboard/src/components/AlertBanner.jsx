function describeAlert(a) {
  const room = a.door_name || `Door #${a.door_id}`;
  if (a.type === "access_requested") {
    return `${room} — access requested${a.requested_by_name ? ` by ${a.requested_by_name}` : ""}`;
  }
  if (a.type === "high_power_empty_room") {
    // Raised by services/energy_service.py: a high-draw device (AC or a
    // plug) is still on while that room's occupancy sensor reports it empty.
    return `${room} — high-power device left on in an empty room`;
  }
  return `${room} — ${a.type}`;
}

export default function AlertBanner({ alerts, onResolve, canResolve }) {
  if (!alerts.length) return null;
  return (
    <div className="alert-banner">
      <strong>{alerts.length} active alert{alerts.length > 1 ? "s" : ""}</strong>
      <ul>
        {alerts.map((a) => (
          <li key={a.alert_id}>
            {describeAlert(a)} ({new Date(a.alert_time).toLocaleTimeString()})
            {canResolve && (
              <button className="link-button" onClick={() => onResolve(a.alert_id)}>
                Resolve
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
