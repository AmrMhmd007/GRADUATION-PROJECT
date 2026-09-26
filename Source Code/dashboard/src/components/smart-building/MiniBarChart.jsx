// Lightweight bar-chart-as-CSS component — no charting library added, since
// the project doesn't already depend on one and this is the only kind of
// chart the Smart Building dashboard needs (a ranked comparison, not a time
// series with axes). `items` is [{ label, value }]; `formatValue` controls
// how the number on the right is displayed (defaults to plain rounding).
export default function MiniBarChart({ items, formatValue = (v) => `${Math.round(v)}`, accent }) {
  if (!items || items.length === 0) {
    return <p className="sb-empty-state" style={{ padding: "12px" }}>No data yet.</p>;
  }
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <div className="sb-chart">
      {items.map((item) => (
        <div className="sb-chart-row" key={item.label}>
          <span className="sb-chart-label" title={item.label}>{item.label}</span>
          <span className="sb-chart-track">
            <span
              className={`sb-chart-bar${accent ? ` accent-${accent}` : ""}`}
              style={{ width: `${Math.max((item.value / max) * 100, item.value > 0 ? 3 : 0)}%` }}
            />
          </span>
          <span className="sb-chart-value">{formatValue(item.value)}</span>
        </div>
      ))}
    </div>
  );
}
