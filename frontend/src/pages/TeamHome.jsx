import { ArrowLeftRight, CreditCard, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { ActivityList, ChallengeRail, StatStrip } from "../components/engage.jsx";
import { Composer, PostFeed } from "../components/Feed.jsx";
import { Empty, ErrorState, Loading, MatchRow, SectionHead, TeamCrest } from "../components/ui.jsx";
import { results } from "../lib/api.js";
import { useFan } from "../lib/fanContext.js";
import { useT } from "../lib/prefs.js";
import { useApi } from "../lib/useApi.js";
import { PollsBlock, PredictionsBlock } from "./FanWars.jsx";

const TABS = ["feed", "fanWars", "me"];

function MySeason({ team }) {
  const t = useT();
  const summary = useApi("/fanpage/me/season-summary");
  const activity = useApi("/fanpage/me/activities");
  const challenges = useApi("/fanpage/me/challenges");
  const ranks = useApi("/fanpage/leaderboard/teams");
  const teamRank = (ranks.data ?? []).find((r) => r.team.id === team.id);
  const s = summary.data;
  return (
    <>
      {summary.loading && <Loading />}
      {summary.error && <ErrorState>{t("state.unavailable")}</ErrorState>}
      {s && (
        <StatStrip stats={[
          [t("me.points"), s.points],
          [t("me.rank"), s.rank ? `#${s.rank}` : "–"],
          [t("me.votes"), s.votes],
          [t("me.predictions"), s.predictions_made],
          [t("me.correct"), s.predictions_correct],
          [t("me.badges"), s.badges_earned],
          [t("rank.teams"), teamRank ? `#${teamRank.rank}` : "–"],
        ]} />
      )}
      <div className="two-col">
        <section className="block">
          <SectionHead title={t("me.history")} />
          {activity.loading ? <Loading /> : <ActivityList items={results(activity.data).slice(0, 12)} />}
        </section>
        <section className="block">
          <SectionHead title={t("chal.title")} />
          {challenges.data && <ChallengeRail challenges={challenges.data} />}
        </section>
      </div>
    </>
  );
}

export default function TeamHome() {
  const t = useT();
  const { profile, status } = useFan();
  const [tab, setTab] = useState("feed");
  const team = profile?.current_team;
  const matches = useApi(team ? `/matches?team=${team.id}&ordering=starts_at` : null);
  const roster = useApi(team ? `/teams/${team.id}/roster` : null);

  if (status === "loading") return <section className="page"><Loading /></section>;
  if (!team) return <Navigate to="/choose-team" replace />;

  const all = results(matches.data);
  const upcoming = all.filter((m) => m.status === "scheduled");
  const recent = all.filter((m) => m.status === "completed").reverse();
  const tabLabel = { feed: t("home.feed"), fanWars: t("home.fanWars"), me: t("home.me") };

  return (
    <>
      <section className="team-banner" style={{ "--team": team.primary_color, "--team-2": team.secondary_color }}>
        <TeamCrest team={team} size={104} />
        <div>
          <p className="eyebrow">{t("home.yourTeam")} · {team.city}</p>
          <h1>{team.name}</h1>
          <p className="lede">{t("home.hi", { name: profile.nickname })}</p>
        </div>
        <nav className="actions" aria-label="Team actions">
          <Link className="btn" to="/meme-zone"><Sparkles size={17} aria-hidden /> {t("nav.memeLab")}</Link>
          <Link className="btn" to="/card"><CreditCard size={17} aria-hidden /> {t("me.card")}</Link>
          <Link className="btn btn-ghost" to="/choose-team"><ArrowLeftRight size={17} aria-hidden /> {t("choose.switch")}</Link>
        </nav>
      </section>

      <div className="tabs" role="tablist">
        {TABS.map((key) => (
          <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{tabLabel[key]}</button>
        ))}
      </div>

      <div className="page-wide">
        {tab === "feed" && (
          <div className="split-layout">
            <div>
              <Composer team={team} />
              <PostFeed teamId={team.id} teamsById={{ [team.id]: team }} canInteract />
            </div>
            <aside>
              <section className="block">
                <SectionHead title={t("home.schedule")} />
                {matches.loading && <Loading />}
                {matches.error && <ErrorState>{t("state.unavailable")}</ErrorState>}
                {!matches.loading && !matches.error && upcoming.length === 0 && <Empty>{t("home.noFixtures")}</Empty>}
                <div className="match-list compact">{upcoming.slice(0, 4).map((m) => <MatchRow key={m.id} match={m} />)}</div>
              </section>
              {recent.length > 0 && (
                <section className="block">
                  <SectionHead title={t("home.results")} />
                  <div className="match-list compact">{recent.slice(0, 3).map((m) => <MatchRow key={m.id} match={m} />)}</div>
                </section>
              )}
              <section className="block">
                <SectionHead title={t("home.squad")} />
                {!roster.loading && results(roster.data).length === 0 && <Empty>{t("home.noSquad")}</Empty>}
                <ul className="roster">
                  {results(roster.data).map((r) => (
                    <li key={r.id}>
                      <span>{r.player_detail.full_name}</span>
                      <small>{r.player_detail.role.replace("_", "-")}{r.is_captain ? " · C" : ""}</small>
                    </li>
                  ))}
                </ul>
              </section>
            </aside>
          </div>
        )}

        {tab === "fanWars" && (
          <div className="two-col">
            <section className="block">
              <SectionHead index={1} title={t("polls.title")} />
              <PollsBlock teamId={team.id} canVote />
            </section>
            <section className="block">
              <SectionHead index={2} title={t("pred.title")} />
              <PredictionsBlock teamId={team.id} canPredict />
            </section>
          </div>
        )}

        {tab === "me" && <MySeason team={team} />}
      </div>
    </>
  );
}
