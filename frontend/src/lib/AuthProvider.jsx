import { useCallback, useEffect, useRef, useState } from "react";

import AuthDialog from "../components/AuthDialog.jsx";
import { authService } from "../services/auth.js";
import { AUTH_REQUIRED_EVENT } from "./api.js";
import { AuthContext } from "./authContext.js";
import { useFeedback } from "./feedbackContext.js";
import { useT } from "./prefs.js";

/**
 * Who is logged in (from the server session) plus the shared login dialog.
 * `openAuth({ reason, onSuccess })` opens it; any 401 from the API opens it too.
 */
export function AuthProvider({ children }) {
  const t = useT();
  const { notify } = useFeedback();
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState("loading");
  const [dialog, setDialog] = useState(null);
  const pending = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const state = await authService.session();
      setUser(state.user);
      setStatus("ready");
      return state.user;
    } catch {
      setUser(null);
      setStatus("error");
      return null;
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const openAuth = useCallback(({ reason, onSuccess } = {}) => {
    pending.current = onSuccess ?? null;
    setDialog({ reason: reason ?? null });
  }, []);
  const closeAuth = useCallback(() => setDialog(null), []);

  useEffect(() => {
    const onAuthRequired = () => {
      setUser(null);
      setDialog((d) => d ?? { reason: t("auth.required") });
    };
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
  }, [t]);

  const logout = useCallback(async () => {
    try {
      await authService.logout();
      notify({ text: t("auth.loggedOut") });
    } catch {
      notify({ type: "error", text: t("auth.logoutFailed") });
    } finally {
      setUser(null);
    }
  }, [notify, t]);

  const welcome = useCallback((u) => {
    const name = u?.display_name || u?.username || u?.email?.split("@")[0] || t("auth.fan");
    notify({ text: t(u?.created ? "auth.welcomeNew" : "auth.welcomeBack", { name }) });
  }, [notify, t]);

  const value = { user, status, refresh, setUser, logout, openAuth, closeAuth };
  return (
    <AuthContext.Provider value={value}>
      {children}
      {dialog && (
        <AuthDialog
          reason={dialog.reason}
          onClose={closeAuth}
          onSuccess={(u) => {
            setDialog(null);
            welcome(u);
            const next = pending.current;
            pending.current = null;
            next?.(u);
          }}
        />
      )}
    </AuthContext.Provider>
  );
}
