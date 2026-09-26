import useEscapeKey from "../../hooks/useEscapeKey";

// Generic confirmation dialog for destructive actions (delete college,
// delete department, etc.) — reused so every "are you sure?" in Academic
// Administration looks and behaves the same way.
export default function ConfirmDialog({ title, message, confirmLabel = "Delete", busy, onConfirm, onCancel }) {
  useEscapeKey(onCancel, !busy);
  return (
    <div className="aa-modal-backdrop" onClick={onCancel}>
      <div className="aa-modal aa-confirm-modal" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <p className="aa-subtitle">{message}</p>
        <div className="aa-confirm-actions">
          <button type="button" className="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="aa-danger-button" onClick={onConfirm} disabled={busy}>
            {busy ? "Deleting…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
