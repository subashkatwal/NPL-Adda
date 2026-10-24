import { AlertTriangle, CheckCircle2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FeedbackContext } from "../lib/feedbackContext.js";

let nextId = 1;

/** In-page confirmation dialog and toast messages for the admin console (no browser popups). */
export function FeedbackProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [dialog, setDialog] = useState(null);
  const confirmButton = useRef(null);

  const dismiss = useCallback((id) => setToasts((all) => all.filter((t) => t.id !== id)), []);

  const notify = useCallback(({ type = "success", text }) => {
    const id = nextId++;
    setToasts((all) => [...all.slice(-3), { id, type, text }]);
    setTimeout(() => dismiss(id), type === "error" ? 8000 : 4000);
  }, [dismiss]);

  const confirm = useCallback((options) => new Promise((resolve) => setDialog({ ...options, resolve })), []);

  const close = useCallback((answer) => {
    setDialog((d) => {
      d?.resolve(answer);
      return null;
    });
  }, []);

  useEffect(() => {
    if (!dialog) return undefined;
    confirmButton.current?.focus();
    const onKey = (e) => e.key === "Escape" && close(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [dialog, close]);

  const value = useMemo(() => ({ notify, confirm }), [notify, confirm]);

  return (
    <FeedbackContext.Provider value={value}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`} role={t.type === "error" ? "alert" : "status"}>
            {t.type === "error" ? <AlertTriangle size={18} aria-hidden /> : <CheckCircle2 size={18} aria-hidden />}
            <span>{t.text}</span>
            <button type="button" aria-label="Dismiss" onClick={() => dismiss(t.id)}><X size={15} aria-hidden /></button>
          </div>
        ))}
      </div>
      {dialog && (
        <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && close(false)}>
          <div className={`dialog confirm-dialog ${dialog.danger ? "is-danger" : ""}`} role="alertdialog" aria-modal="true"
            aria-labelledby="confirm-title" aria-describedby="confirm-text">
            <h2 id="confirm-title">{dialog.title ?? "Are you sure?"}</h2>
            {dialog.message && <p id="confirm-text" className="lede">{dialog.message}</p>}
            <div className="actions">
              <button ref={confirmButton} type="button" className={`btn ${dialog.danger ? "btn-danger-solid" : "btn-primary"}`}
                onClick={() => close(true)}>{dialog.confirmLabel ?? "Confirm"}</button>
              <button type="button" className="btn" onClick={() => close(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </FeedbackContext.Provider>
  );
}
