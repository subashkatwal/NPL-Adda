import { Loader2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "../lib/authContext.js";
import { useT } from "../lib/prefs.js";
import { authService } from "../services/auth.js";
import GoogleButton from "./GoogleButton.jsx";
import { ErrorState, Logo, PasswordInput } from "./ui.jsx";

const ERROR_KEYS = {
  invalid_credentials: "auth.err.invalid",
  use_google: "auth.err.useGoogle",
  account_exists_unverified: "auth.err.exists",
  google_already_linked: "auth.err.linked",
  google_not_configured: "auth.googleOff",
  invalid_google_token: "auth.err.google",
  google_email_unverified: "auth.err.googleEmail",
  account_disabled: "auth.err.disabled",
};

/** Login / register dialog. Opened by the header, by protected actions and by any 401. */
export default function AuthDialog({ reason, onClose, onSuccess }) {
  const t = useT();
  const { setUser } = useAuth();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", display_name: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const firstField = useRef(null);

  useEffect(() => {
    firstField.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, mode]);

  function explain(err) {
    if (err?.status === 429) return t("auth.err.limited");
    const key = ERROR_KEYS[err?.data?.code];
    if (key) return t(key);
    if (err?.data?.email) return String(err.data.email[0]);
    if (err?.data?.password) return String(err.data.password[0]);
    return err?.message || t("state.error");
  }

  async function finish(promise) {
    setBusy(true);
    setError(null);
    try {
      const user = await promise;
      setUser(user);
      onSuccess?.(user);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(false);
    }
  }

  function submit(event) {
    event.preventDefault();
    const email = form.email.trim();
    if (mode === "login") return finish(authService.login(email, form.password));
    return finish(authService.register({ email, password: form.password, display_name: form.display_name.trim() })
      .then((user) => ({ ...user, created: true })));
  }

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title">
        <button type="button" className="icon-btn dialog-close" onClick={onClose} aria-label={t("auth.close")}>
          <X size={18} aria-hidden />
        </button>
        <Logo />
        <h2 id="auth-title">{t(mode === "login" ? "auth.loginTitle" : "auth.registerTitle")}</h2>
        {reason && <p className="lede">{reason}</p>}

        <GoogleButton onCredential={(credential) => finish(authService.google(credential))}
          onError={(err) => setError(err.message)} />

        <div className="divider"><span>{t("auth.or")}</span></div>

        <form onSubmit={submit} noValidate={false}>
          {mode === "register" && (
            <label>{t("auth.name")}
              <input value={form.display_name} onChange={set("display_name")} maxLength={60} autoComplete="name" />
            </label>
          )}
          <label>{t("auth.email")}
            <input ref={firstField} type="email" value={form.email} onChange={set("email")} required autoComplete="email" />
          </label>
          <label>{t("auth.password")}
            <PasswordInput value={form.password} onChange={set("password")} required
              minLength={mode === "register" ? 8 : 1} autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </label>
          {mode === "register" && <p className="meta">{t("auth.passwordHint")}</p>}
          {error && <ErrorState>{error}</ErrorState>}
          <button className="btn btn-primary btn-block" disabled={busy || !form.email || !form.password}>
            {busy && <Loader2 className="spin" size={17} aria-hidden />}
            {t(mode === "login" ? "auth.loginCta" : "auth.registerCta")}
          </button>
        </form>

        <p className="dialog-switch">
          {t(mode === "login" ? "auth.noAccount" : "auth.haveAccount")}{" "}
          <button type="button" className="link-btn strong" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>
            {t(mode === "login" ? "auth.registerLink" : "auth.loginLink")}
          </button>
        </p>
      </div>
    </div>
  );
}
