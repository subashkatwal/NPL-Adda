import { ArrowRight, Flame, IdCard, MessageSquareQuote, Trophy } from "lucide-react";
import { Link } from "react-router-dom";

import Hero from "../components/Hero.jsx";
import { Empty, ErrorState, Loading, MatchRow, PersonaPill, SectionHead, TeamCrest } from "../components/ui.jsx";
import { results } from "../lib/api.js";
import { useFan } from "../lib/fanContext.js";
import { useT } from "../lib/prefs.js";
import { useApi } from "../lib/useApi.js";

// What fans can actually do here; every card links to a working feature.
const ACTIONS = [
  { key: "predict", icon: Trophy, to: "/fan-wars" },
  { key: "memes", icon: Flame, to: "/meme-zone" },
  { key: "card", icon: IdCard, to: "/card" },
];

export default function Landing() {
  const t = useT();
  const { profile } = useFan();
  const upcoming = useApi("/matches?status=scheduled&ordering=starts_at");
  const teams = useApi("/teams");
  const posts = useApi("/content?ordering=-published_at");
  const leaders = useApi("/fanpage/leaderboard?page_size=5");
  const livePosts = results(posts.data).slice(0, 3);
  const topFans = results(leaders.data).filter((f) => f.points > 0).slice(0, 5);

  return (
    <>
      <Hero to={profile?.current_team ? "/home" : "/choose-team"} label={t(profile?.current_team ? "hero.back" : "hero.enter")} />

      <section className="band" id="teams">
        <SectionHead index={1} title={t("landing.pick")}
          aside={<Link to="/choose-team" className="text-link">{t("landing.allTeams")} <ArrowRight size={16} aria-hidden /></Link>} />
        {teams.loading && <Loading />}
        {teams.error && <ErrorState>{t("state.unavailable")}</ErrorState>}
        <ul className="team-strip">
          {results(teams.data).map((team) => (
            <li key={team.id} style={{ "--team": team.primary_color }}>
              <Link to={`/choose-team?team=${team.id}`} title={team.name}>
                <TeamCrest team={team} size={52} />
                <span>{team.short_name}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="band">
        <SectionHead index={2} title={t("landing.upcoming")}
          aside={<Link to="/matches" className="text-link">{t("landing.allMatches")} <ArrowRight size={16} aria-hidden /></Link>} />
        {upcoming.loading && <Loading />}
        {!upcoming.loading && results(upcoming.data).length === 0 && !upcoming.error && <Empty>{t("landing.noFixtures")}</Empty>}
        {upcoming.error && <ErrorState>{t("state.unavailable")}</ErrorState>}
        <div className="match-list">{results(upcoming.data).slice(0, 4).map((m) => <MatchRow key={m.id} match={m} />)}</div>
      </section>

      <section className="band">
        <SectionHead index={3} title={t("landing.play")} />
        <div className="stands">
          {ACTIONS.map((action, i) => (
            <Link key={action.key} to={action.to} className="stand-item stand-link">
              <span className="stand-num">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <h3><action.icon size={18} aria-hidden /> {t(`landing.${action.key}.title`)}</h3>
                <p>{t(`landing.${action.key}.body`)}</p>
                <span className="text-link">{t(`landing.${action.key}.cta`)} <ArrowRight size={15} aria-hidden /></span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {topFans.length > 0 && (
        <section className="band">
          <SectionHead index={4} title={t("landing.topFans")}
            aside={<Link to="/fan-wars" className="text-link">{t("landing.fullTable")} <ArrowRight size={16} aria-hidden /></Link>} />
          <ol className="ranking ranking-fans">
            {topFans.map((fan) => (
              <li key={fan.id}>
                <span className="rank-num">{fan.rank}</span>
                <Link className="rank-name" to={`/fans/${fan.id}`}>{fan.nickname}</Link>
                <span className="rank-sub"><PersonaPill personality={fan.fan_personality} chip /></span>
                <span className="rank-val">{fan.points} <small>pts</small></span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {livePosts.length > 0 && (
        <section className="band">
          <SectionHead index={topFans.length > 0 ? 5 : 4} title={t("landing.stands")} />
          <div className="stands">
            {livePosts.map((post, i) => (
              <article key={post.id} className="stand-item">
                <span className="stand-num">{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <h3><MessageSquareQuote size={18} aria-hidden /> {post.title || post.author_nickname}</h3>
                  <p>{post.body}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
