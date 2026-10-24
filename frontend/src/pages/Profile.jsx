import { ArrowLeftRight, CreditCard, Trophy } from "lucide-react";
import { Link, Navigate } from "react-router-dom";

import { ActivityList, StatStrip } from "../components/engage.jsx";
import { BackLink, Empty, ErrorState, Loading, SectionHead, TeamCrest } from "../components/ui.jsx";
import { PERSONALITY_LABELS } from "../i18n/strings.js";
import { results } from "../lib/api.js";
import { useFan } from "../lib/fanContext.js";
import { matchDate } from "../lib/format.js";
import { usePrefs, useT } from "../lib/prefs.js";
import { useApi } from "../lib/useApi.js";

export default function Profile() {
  const t = useT();
  const { lang } = usePrefs();
  const { profile, status } = useFan();
  const summary = useApi(profile ? "/fanpage/me/season-summary" : null);
  const activity = useApi(profile ? "/fanpage/me/activities" : null);
  const badges = useApi(profile ? "/fanpage/me/badges" : null);
  const memberships = useApi(profile ? "/fanpage/me/memberships" : null);
  const posts = useApi(profile ? "/content/mine" : null);
  const drafts = useApi(profile ? "/memelab/drafts?status=draft" : null);

  if (status === "loading") return <section className="page"><Loading /></section>;
  if (!profile) return <Navigate to="/choose-team" replace />;
  const team = profile.current_team;
  const s = summary.data;

  return (
    <div className="page-wide">
      <BackLink fallback="/home" />
      <header className="profile-head" style={team ? { "--team": team.primary_color } : undefined}>
        {team && <TeamCrest team={team} size={88} />}
        <div>
          <p className="eyebrow">{PERSONALITY_LABELS[lang][profile.fan_personality]}</p>
          <h1>{profile.nickname}</h1>
          <p className="lede">{team ? team.name : t("choose.pick")}</p>
        </div>
        <div className="actions">
          <Link className="btn btn-primary" to="/card"><CreditCard size={17} aria-hidden /> {t("me.openCard")}</Link>
          <Link className="btn btn-ghost" to="/choose-team"><ArrowLeftRight size={17} aria-hidden /> {t("choose.switch")}</Link>
        </div>
      </header>

      {summary.error && <ErrorState>{t("state.unavailable")}</ErrorState>}
      {s && (
        <StatStrip stats={[
          [t("me.points"), s.points],
          [t("me.rank"), s.rank ? `#${s.rank}` : "–"],
          [t("me.votes"), s.votes],
          [t("me.predictions"), s.predictions_made],
          [t("me.correct"), s.predictions_correct],
          [t("me.badges"), s.badges_earned],
        ]} />
      )}

      <div className="two-col">
        <section className="block">
          <SectionHead index={1} title={t("me.badges")} />
          {badges.loading && <Loading />}
          {!badges.loading && (badges.data ?? []).length === 0 && <Empty>{t("me.noHistory")}</Empty>}
          <ul className="badge-shelf">
            {(badges.data ?? []).map((b) => (
              <li key={b.id}><Trophy size={18} aria-hidden /><strong>{b.badge.name}</strong><span>{b.badge.description}</span></li>
            ))}
          </ul>
        </section>

        <section className="block">
          <SectionHead index={2} title={t("me.memberships")} />
          <ol className="activity">
            {results(memberships.data).map((m) => (
              <li key={m.id}>
                <time>{matchDate(m.joined_at)}</time>
                <span>{m.team_detail.name}</span>
                <span className="delta">{m.left_at ? matchDate(m.left_at) : t("me.current")}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="block">
          <SectionHead index={3} title={t("me.history")} />
          {activity.loading ? <Loading /> : <ActivityList items={results(activity.data).slice(0, 15)} />}
        </section>

        <section className="block">
          <SectionHead index={4} title={t("me.content")} />
          {!posts.loading && results(posts.data).length === 0 && <Empty>{t("me.noContent")}</Empty>}
          <ol className="activity">
            {results(posts.data).map((p) => (
              <li key={p.id}>
                <time>{matchDate(p.created_at)}</time>
                <span className="clip">{p.title || p.body}</span>
                <span className={`chip status-chip s-${p.status}`}>{p.status.replace("_", " ")}</span>
              </li>
            ))}
          </ol>
          <SectionHead title={t("me.drafts")} />
          {!drafts.loading && results(drafts.data).length === 0 && <Empty>{t("me.noDrafts")}</Empty>}
          <ol className="activity">
            {results(drafts.data).map((d) => (
              <li key={d.id}><time>{matchDate(d.created_at)}</time><span className="clip">{d.caption}</span><Link to="/meme-zone">{t("nav.memeLab")}</Link></li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  );
}
