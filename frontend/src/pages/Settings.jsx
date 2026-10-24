import { Check, KeyRound, LogOut, Save, Unlink } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import GoogleButton from "../components/GoogleButton.jsx";
import { Avatar } from "../components/UserMenu.jsx";
import { BackLink, ErrorState, Loading, LoginPrompt, PrefToggles, SectionHead } from "../components/ui.jsx";
import { useAuth } from "../lib/authContext.js";
import { useT } from "../lib/prefs.js";
import { authService } from "../services/auth.js";

export default function Settings() {
  const t = useT();
  const navigate = useNavigate();
  const { user, status, setUser, logout } = useAuth();
  const [form, setForm] = useState(null);
  const [msg, setMsg] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  if (status === "loading") return <section className="page"><Loading /></section>;
  if (!user) return <section className="page"><h1>{t("nav.settings")}</h1><LoginPrompt /></section>;

  const values = form ?? { display_name: user.display_name, username: user.username ?? "" };
  const google = user.providers.includes("google");

  async function run(fn, success) {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      setUser(await fn());
      setMsg(success);
      setForm(null);
    } catch (err) {
      setError(err.data?.detail || err.data?.username?.[0] || err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page settings">
      <BackLink fallback="/profile" />
      <h1>{t("nav.settings")}</h1>

      <div className="settings-grid">
        <section className="block">
          <SectionHead index={1} title={t("settings.account")} />
          <div className="account-row">
            <Avatar user={user} size={56} />
            <div><strong>{user.display_name || t("auth.fan")}</strong><span className="meta">{user.email}</span></div>
          </div>
          <form className="profile-fields" onSubmit={(e) => {
            e.preventDefault();
            run(() => authService.updateMe({ display_name: values.display_name.trim(), username: values.username.trim() || null }), t("settings.saved"));
          }}>
            <label>{t("auth.name")}
              <input value={values.display_name} maxLength={60} onChange={(e) => setForm({ ...values, display_name: e.target.value })} />
            </label>
            <label>{t("settings.username")}
              <input value={values.username} maxLength={30} pattern="[A-Za-z0-9_]{3,30}" placeholder="rhino_roar"
                onChange={(e) => setForm({ ...values, username: e.target.value })} />
            </label>
            <button className="btn btn-primary" disabled={busy || !form}><Save size={16} aria-hidden /> {t("settings.save")}</button>
          </form>
        </section>

        <section className="block">
          <SectionHead index={2} title={t("settings.signIn")} />
          <ul className="methods">
            <li>
              <KeyRound size={18} aria-hidden />
              <span>{t("settings.password")}</span>
              <span className="meta">{user.has_password ? <><Check size={14} aria-hidden /> {t("settings.on")}</> : t("settings.off")}</span>
            </li>
            <li>
              <span className="g-dot" aria-hidden>G</span>
              <span>Google</span>
              <span className="meta">{google ? <><Check size={14} aria-hidden /> {t("settings.linked")}</> : t("settings.notLinked")}</span>
            </li>
          </ul>
          {google ? (
            <button className="btn btn-ghost" disabled={busy} onClick={() => run(authService.unlinkGoogle, t("settings.unlinked"))}>
              <Unlink size={16} aria-hidden /> {t("settings.unlink")}
            </button>
          ) : (
            <div className="link-google">
              <p className="meta">{t("settings.linkHint")}</p>
              <GoogleButton text="signin_with" onCredential={(c) => run(() => authService.linkGoogle(c), t("settings.linkedOk"))}
                onError={(err) => setError(err.message)} />
            </div>
          )}
        </section>

        <section className="block">
          <SectionHead index={3} title={t("settings.prefs")} />
          <PrefToggles />
          <div className="actions">
            <button className="btn" onClick={async () => { await logout(); navigate("/"); }}>
              <LogOut size={16} aria-hidden /> {t("auth.logout")}
            </button>
          </div>
        </section>
      </div>
      {msg && <p className="state" role="status">{msg}</p>}
      {error && <ErrorState>{error}</ErrorState>}
    </section>
  );
}
