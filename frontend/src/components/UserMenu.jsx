import { Home, LogIn, LogOut, Settings, ShieldCheck, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../lib/authContext.js";
import { useT } from "../lib/prefs.js";

export function Avatar({ user, size = 34 }) {
  const name = user.display_name || user.email;
  const initials = name.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
  return user.avatar_url ? (
    <img className="avatar" src={user.avatar_url} alt="" width={size} height={size} referrerPolicy="no-referrer" />
  ) : (
    <span className="avatar avatar-initials" style={{ width: size, height: size }} aria-hidden>{initials}</span>
  );
}

/** Login button when logged out; avatar + menu (Profile, My Team, Settings, Logout) when logged in. */
export default function UserMenu() {
  const t = useT();
  const navigate = useNavigate();
  const { user, status, openAuth, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => !ref.current?.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (status === "loading") return <span className="avatar avatar-skeleton" aria-hidden />;
  if (!user) {
    return (
      <button type="button" className="btn btn-primary btn-sm" onClick={() => openAuth()}>
        <LogIn size={15} aria-hidden /> {t("auth.login")}
      </button>
    );
  }

  async function onLogout() {
    setOpen(false);
    await logout();
    navigate("/");
  }

  return (
    <div className="user-menu" ref={ref}>
      <button type="button" className="avatar-btn" aria-haspopup="menu" aria-expanded={open}
        aria-label={t("auth.menu")} onClick={() => setOpen((o) => !o)}>
        <Avatar user={user} />
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head">
            <strong>{user.display_name || t("auth.fan")}</strong>
            <span>{user.email}</span>
          </div>
          <Link role="menuitem" to="/profile" onClick={() => setOpen(false)}><User size={16} aria-hidden /> {t("nav.profile")}</Link>
          <Link role="menuitem" to="/home" onClick={() => setOpen(false)}><Home size={16} aria-hidden /> {t("nav.myTeam")}</Link>
          <Link role="menuitem" to="/settings" onClick={() => setOpen(false)}><Settings size={16} aria-hidden /> {t("nav.settings")}</Link>
          {user.is_staff && (
            <Link role="menuitem" to="/staff" onClick={() => setOpen(false)}><ShieldCheck size={16} aria-hidden /> {t("nav.admin")}</Link>
          )}
          <button role="menuitem" type="button" onClick={onLogout}><LogOut size={16} aria-hidden /> {t("auth.logout")}</button>
        </div>
      )}
    </div>
  );
}
