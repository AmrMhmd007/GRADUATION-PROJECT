export default function AlertBanner({ alerts, onResolve, canResolve }) {
  if (!alerts.length) return null;
  return (
    <div className="alert-banner">
      <strong>{alerts.length} active alert{alerts.length > 1 ? "s" : ""}</strong>
      <ul>
        {alerts.map((a) => (
          <li key={a.alert_id}>
            Door #{a.door_id} &mdash; {a.type} ({new Date(a.alert_time).toLocaleTimeString()})
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
