import { ArrowRight, Flag, Inbox, UserPlus } from "lucide-react";
import { Link } from "react-router-dom";

import { Empty, ErrorState, Loading } from "../../components/ui.jsx";
import { timeAgo } from "../../lib/format.js";
import { useApi } from "../../lib/useApi.js";

const TILES = [
  ["users", "Users", "/staff/users", (t) => `+${t.users_new_7d} this week`],
  ["fans", "Fan profiles", "/staff/fan-profiles"],
  ["teams", "Active teams", "/staff/teams", (t) => `${t.players} active players`],
  ["matches_upcoming", "Upcoming matches", "/staff/matches?status=scheduled", (t) => `${t.matches_live} live now`],
  ["posts_pending", "Posts to review", "/staff/posts?status=pending_review"],
  ["reports_open", "Open reports", "/staff/reports?status=open"],
  ["posts_published", "Published posts", "/staff/posts?status=published"],
  ["memes_drafts", "Meme drafts", "/staff/meme-drafts", (t) => `${t.memes_7d} captions this week`],
  ["polls_open", "Open polls", "/staff/polls?status=open"],
  ["predictions", "Predictions", "/staff/predictions"],
  ["points_7d", "Points earned (7 days)", "/staff/activities"],
  ["staff", "Staff accounts", "/staff/users?is_staff=true"],
];

export default function Dashboard() {
  const { data, error, loading } = useApi("/admin/dashboard");
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} />;
  const { totals } = data;
  const maxMembers = Math.max(1, ...data.teams.map((t) => t.members));

  return (
    <>
      <header className="admin-head">
        <div>
          <p className="eyebrow">Overview</p>
          <h1>Dashboard</h1>
        </div>
      </header>

      <div className="admin-tiles">
        {TILES.map(([key, label, to, sub]) => (
          <Link key={key} to={to} className={`admin-tile ${(key === "posts_pending" || key === "reports_open") && totals[key] ? "is-alert" : ""}`}>
            <span className="admin-tile-label">{label}</span>
            <strong>{totals[key].toLocaleString()}</strong>
            {sub && <small>{sub(totals)}</small>}
          </Link>
        ))}
      </div>

      <div className="admin-panels">
        <section className="admin-panel">
          <h2><Inbox size={18} aria-hidden /> Review queue</h2>
          {data.pending_posts.length === 0 ? <Empty>Nothing waiting for review.</Empty> : (
            <ul className="admin-queue">
              {data.pending_posts.map((p) => (
                <li key={p.id}>
                  <Link to={`/staff/posts/${p.id}`}>{p.title}</Link>
                  <span>{p.author} · {p.content_type.replace("_", " ")} · {timeAgo(p.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
          <Link className="text-link" to="/staff/posts?status=pending_review">All pending posts <ArrowRight size={15} aria-hidden /></Link>
        </section>

        <section className="admin-panel">
          <h2><Flag size={18} aria-hidden /> Open reports</h2>
          {data.open_reports.length === 0 ? <Empty>No open reports.</Empty> : (
            <ul className="admin-queue">
              {data.open_reports.map((r) => (
                <li key={r.id}>
                  <Link to={`/staff/reports/${r.id}`}>{r.reason}</Link>
                  <span>on “{r.post}” · {timeAgo(r.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
          <Link className="text-link" to="/staff/reports?status=open">All reports <ArrowRight size={15} aria-hidden /></Link>
        </section>

        <section className="admin-panel">
          <h2>Fans per team</h2>
          {data.teams.length === 0 ? <Empty>No active teams.</Empty> : (
            <ul className="admin-bars">
              {data.teams.map((t) => (
                <li key={t.id}>
                  <Link to={`/staff/teams/${t.id}`}>{t.name}</Link>
                  <span className="admin-bar"><i style={{ width: `${(t.members / maxMembers) * 100}%`, background: t.primary_color }} /></span>
                  <strong>{t.members}</strong>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="admin-panel">
          <h2><UserPlus size={18} aria-hidden /> Newest accounts</h2>
          <ul className="admin-queue">
            {data.recent_users.map((u) => (
              <li key={u.id}>
                <Link to={`/staff/users/${u.id}`}>{u.display_name || u.email}</Link>
                <span>{u.email} · joined {timeAgo(u.date_joined)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
