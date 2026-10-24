import { Link } from "react-router-dom";

import { ChallengeRail, FanRanking, PollCard, PredictionCard, PredictionSplit, TeamRanking } from "../components/engage.jsx";
import { BackLink, Empty, ErrorState, Loading, LoginPrompt, SectionHead } from "../components/ui.jsx";
import { results } from "../lib/api.js";
import { useAuth } from "../lib/authContext.js";
import { useFan } from "../lib/fanContext.js";
import { useT } from "../lib/prefs.js";
import { useApi } from "../lib/useApi.js";

export function PredictionsBlock({ teamId, canPredict }) {
  const t = useT();
  const upcoming = useApi(`/matches?status=scheduled&ordering=starts_at${teamId ? `&team=${teamId}` : ""}`);
  const mine = useApi(canPredict ? "/fanpage/predictions" : null);
  if (upcoming.loading) return <Loading />;
  if (upcoming.error) return <ErrorState>{t("state.unavailable")}</ErrorState>;
  const matches = results(upcoming.data).filter((m) => new Date(m.starts_at) > new Date());
  if (!matches.length) return <Empty>{t("pred.empty")}</Empty>;
  const byMatch = Object.fromEntries(results(mine.data).map((p) => [p.match, p]));
  return (
    <div className="prediction-list">
      {matches.slice(0, 6).map((m) => (
        <PredictionCard key={m.id} match={m} existing={byMatch[m.id]} canPredict={canPredict && !mine.loading} />
      ))}
    </div>
  );
}

export function PollsBlock({ teamId, canVote }) {
  const t = useT();
  const polls = useApi(`/fanpage/polls?status=open${teamId ? `&team=${teamId}` : ""}`);
  if (polls.loading) return <Loading />;
  if (polls.error) return <ErrorState>{t("state.unavailable")}</ErrorState>;
  const list = results(polls.data);
  if (!list.length) return <Empty>{t("polls.empty")}</Empty>;
  return <div className="poll-list">{list.map((p) => <PollCard key={p.id} poll={p} canVote={canVote} />)}</div>;
}

function RecentSplits() {
  const recent = useApi("/matches?status=completed&ordering=-starts_at");
  const list = results(recent.data).slice(0, 3);
  if (!list.length) return null;
  return (
    <ul className="recent-splits">
      {list.map((m) => (
        <li key={m.id}>
          <span>{m.home_team_detail.short_name} vs {m.away_team_detail.short_name}</span>
          <PredictionSplit matchId={m.id} />
        </li>
      ))}
    </ul>
  );
}

export default function FanWars() {
  const t = useT();
  const { profile } = useFan();
  const { user } = useAuth();
  const teamRanks = useApi("/fanpage/leaderboard/teams");
  const fanRanks = useApi("/fanpage/leaderboard");
  const challenges = useApi(profile ? "/fanpage/me/challenges" : null);
  const canPlay = Boolean(profile);

  return (
    <div className="page-wide">
      <header className="page-head">
        <BackLink fallback="/" />
        <p className="eyebrow">{t("nav.fanWars")}</p>
        <h1>{t("nav.fanWars")}</h1>
        {!user && <LoginPrompt message={t("auth.playReason")} />}
        {user && !canPlay && (
          <p className="lede">{t("state.needProfile")} <Link to="/choose-team">{t("choose.pick")} →</Link></p>
        )}
      </header>

      <div className="split-layout">
        <div>
          <section className="block">
            <SectionHead index={1} title={t("polls.title")} />
            <PollsBlock canVote={canPlay} />
          </section>
          <section className="block">
            <SectionHead index={2} title={t("pred.title")} aside={<span className="meta">{t("pred.free")}</span>} />
            <PredictionsBlock canPredict={canPlay} />
            <RecentSplits />
          </section>
        </div>

        <aside>
          <section className="block">
            <SectionHead index={3} title={t("rank.teams")} />
            {teamRanks.loading && <Loading />}
            {teamRanks.error && <ErrorState>{t("state.unavailable")}</ErrorState>}
            {teamRanks.data && <TeamRanking rows={teamRanks.data} highlight={profile?.current_team?.id} />}
          </section>
          <section className="block">
            <SectionHead index={4} title={t("rank.fans")} />
            {fanRanks.loading && <Loading />}
            {fanRanks.error && <ErrorState>{t("state.unavailable")}</ErrorState>}
            {fanRanks.data && <FanRanking rows={results(fanRanks.data).slice(0, 10)} meId={profile?.id} />}
          </section>
          {profile && (
            <section className="block">
              <SectionHead index={5} title={t("chal.title")} />
              {challenges.loading && <Loading />}
              {challenges.error && <ErrorState>{t("state.unavailable")}</ErrorState>}
              {challenges.data && <ChallengeRail challenges={challenges.data} />}
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
