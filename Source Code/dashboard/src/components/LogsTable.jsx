export default function LogsTable({ logs, title = "Recent Access Events" }) {
  return (
    <div className="logs-panel">
      <h2>{title}</h2>
      {logs.length === 0 ? (
        <p className="muted">No events yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Door</th>
              <th>Credential</th>
              <th>Method</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((e) => (
              <tr key={e.event_id}>
                <td>{new Date(e.event_time).toLocaleTimeString()}</td>
                <td>#{e.door_id}</td>
                <td>{e.credential_id ?? "-"}</td>
                <td>{e.method}</td>
                <td className={e.result === "granted" ? "ok" : "bad"}>{e.result}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
