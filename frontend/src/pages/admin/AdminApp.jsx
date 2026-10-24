import { LayoutDashboard, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";

import { ErrorState, Loading, LoginPrompt } from "../../components/ui.jsx";
import { useAuth } from "../../lib/authContext.js";
import { useApi } from "../../lib/useApi.js";
import { adminService } from "../../services/admin.js";
import Dashboard from "./Dashboard.jsx";
import ResourceEdit from "./ResourceEdit.jsx";
import ResourceList from "./ResourceList.jsx";

function groupResources(resources) {
  const groups = new Map();
  resources.forEach((r) => groups.set(r.group, [...(groups.get(r.group) ?? []), r]));
  return [...groups.entries()];
}

/** Staff-only console at /staff: dashboard plus list/edit pages for every resource the API exposes. */
export default function AdminApp() {
  const { user, status } = useAuth();
  const index = useApi(user?.is_staff ? "/admin/resources" : null);
  const attention = useAttention(Boolean(user?.is_staff));

  if (status === "loading") return <div className="page"><Loading /></div>;
  if (!user) {
    return (
      <div className="page">
        <p className="eyebrow">Admin</p>
        <h1>Staff console</h1>
        <LoginPrompt message="Log in with a staff account to open the admin console." />
      </div>
    );
  }
  if (!user.is_staff) {
    return (
      <div className="page">
        <p className="eyebrow">Admin</p>
        <h1>Staff console</h1>
        <ErrorState>This area is only for staff accounts.</ErrorState>
      </div>
    );
  }
  if (index.loading || !index.data) {
    return <div className="page">{index.error ? <ErrorState error={index.error} /> : <Loading />}</div>;
  }

  const { resources, me } = index.data;
  const byKey = Object.fromEntries(resources.map((r) => [r.key, r]));
  return (
    <div className="admin">
      <aside className="admin-nav" aria-label="Admin sections">
        <div className="admin-brand">
          <ShieldCheck size={18} aria-hidden />
          <span>Admin</span>
          <small>{me.is_superuser ? "Superuser" : me.is_moderator ? "Staff · moderator" : "Staff"}</small>
        </div>
        <NavLink to="/staff" end className="admin-link"><LayoutDashboard size={16} aria-hidden /> Dashboard</NavLink>
        {groupResources(resources).map(([group, items]) => (
          <div key={group} className="admin-group">
            <p>{group}</p>
            {items.map((r) => (
              <NavLink key={r.key} to={`/staff/${r.key}`} className="admin-link">
                {r.label}<NavBadge counts={attention.counts[r.key]} />
              </NavLink>
            ))}
          </div>
        ))}
      </aside>
      <section className="admin-main">
        <Routes>
          <Route index element={<Dashboard />} />
          <Route path=":resource" element={<ResourceList resources={byKey} onSeen={attention.seen} onChanged={attention.refresh} />} />
          <Route path=":resource/:id" element={<ResourceEdit resources={byKey} me={me} onChanged={attention.refresh} />} />
        </Routes>
      </section>
    </div>
  );
}

/** Red count: rows waiting for review, or rows added since you last opened the section. */
function NavBadge({ counts }) {
  if (!counts) return null;
  const pending = counts.pending ?? 0;
  const fresh = counts.new ?? 0;
  const value = pending || fresh;
  if (!value) return null;
  const title = pending ? `${pending} waiting for review` : `${fresh} new since your last visit`;
  return <span className={`admin-badge ${pending ? "is-pending" : ""}`} title={title} aria-label={title}>{value > 99 ? "99+" : value}</span>;
}

const POLL_MS = 60_000;

/** Polls /admin/attention; `seen(key)` clears a section's "new" count when it is opened. */
function useAttention(enabled) {
  const [counts, setCounts] = useState({});
  const refresh = useCallback(() => {
    if (!enabled) return;
    adminService.attention().then(setCounts).catch(() => {});
  }, [enabled]);
  const seen = useCallback((key) => {
    setCounts((c) => (c[key]?.new ? { ...c, [key]: { ...c[key], new: 0 } } : c));
    adminService.markSeen(key).catch(() => {});
  }, []);
  useEffect(() => {
    refresh();
    if (!enabled) return undefined;
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [enabled, refresh]);
  return { counts, refresh, seen };
}
