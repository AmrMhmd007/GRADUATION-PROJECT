import { useEffect } from "react";

// Stage E-hardening / E15 (accessibility): every modal in this app closes on
// a backdrop click, but none of them responded to Escape — a real keyboard-
// only gap. One small shared hook rather than duplicating the same
// addEventListener/cleanup in every modal component.
export default function useEscapeKey(onClose, active = true) {
  useEffect(() => {
    if (!active || !onClose) return undefined;
    function handleKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, active]);
}
