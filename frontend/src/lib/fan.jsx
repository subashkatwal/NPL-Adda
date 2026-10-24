import { useCallback, useEffect, useState } from "react";

import { api } from "./api.js";
import { useAuth } from "./authContext.js";
import { FanContext } from "./fanContext.js";

/** The logged-in user's fan profile from the backend (the source of truth for membership). */
export function FanProvider({ children }) {
  const { user, status: authStatus } = useAuth();
  const [profile, setProfile] = useState(null);
  const [status, setStatus] = useState("loading");

  const refresh = useCallback(async () => {
    if (!user) {
      setProfile(null);
      setStatus("ready");
      return null;
    }
    try {
      const me = await api("/fanpage/me", { silent401: true });
      setProfile(me);
      setStatus("ready");
      return me;
    } catch (err) {
      setProfile(null);
      setStatus([401, 403, 404].includes(err.status) ? "ready" : "error");
      return null;
    }
  }, [user]);

  useEffect(() => {
    if (authStatus !== "loading") refresh();
  }, [authStatus, refresh]);

  return (
    <FanContext.Provider value={{ profile, status: authStatus === "loading" ? "loading" : status, refresh, setProfile }}>
      {children}
    </FanContext.Provider>
  );
}
