import { Swords } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Empty, ErrorState, Loading, TeamCrest } from "../../components/ui.jsx";
import { useApi } from "../../lib/useApi.js";
import { MemeGrid } from "./Feed.jsx";
import { PhaseBadge } from "./Contests.jsx";

const PERIODS = { week: "This week", month: "This month", season: "Season", all: "All time" };

export function PeriodTabs({ period, setPeriod }) {
  return (
    <div className="segmented" role="tablist" aria-label="Period">
      {Object.entries(PERIODS).map(([v, l]) => (
        <button key={v} role="tab" aria-selected={period === v} onClick={() => setPeriod(v)}>{l}</button>
      ))}
    </div>
  );
}

/** Rival fan bases ranked by their memes' engagement; pick two teams to compare head to head. */
export default function TeamWars() {
  const [period, setPeriod] = useState("week");
  const [focus, setFocus] = useState(null);
  const wars = useApi(`/memelab/team-wars?period=${period}`);
  const teams = wars.data?.teams ?? [];
  const max = Math.max(1, ...teams.map((t) => t.score));
  const [a, b] = [teams[0], teams[1]];

  return (
    <div className="mz-wars">
      <div className="mz-toolbar"><PeriodTabs period={period} setPeriod={setPeriod} /></div>
      {wars.loading && <Loading />}
      {wars.error && <ErrorState>Team Wars couldn't load.</ErrorState>}
      {a && b && (a.score > 0 || b.score > 0) && (
        <div className="mz-versus" style={{ "--a": a.primary_color, "--b": b.primary_color }}>
          <div><TeamCrest team={{ ...a, name: a.name }} size={56} /><strong>{a.name}</strong><span>{a.score} pts · {a.memes} memes</span></div>
          <Swords size={32} aria-hidden />
          <div><TeamCrest team={{ ...b, name: b.name }} size={56} /><strong>{b.name}</strong><span>{b.score} pts · {b.memes} memes</span></div>
        </div>
      )}
      {teams.length > 0 && (
        <ol className="mz-war-table">
          {teams.map((t) => (
            <li key={t.team_id} className={focus === t.team_id ? "is-on" : ""}>
              <span className="rank-num">{t.rank}</span>
              <TeamCrest team={t} size={34} />
              <button type="button" className="mz-war-name" onClick={() => setFocus(focus === t.team_id ? null : t.team_id)}
                aria-pressed={focus === t.team_id}>{t.name}<small>{t.members} fans · {t.memes} memes</small></button>
              <span className="mz-war-bar"><i style={{ width: `${(t.score / max) * 100}%`, background: t.primary_color }} /></span>
              <strong>{t.score}</strong>
            </li>
          ))}
        </ol>
      )}
      <p className="meta">{wars.data?.label}: team score = sum of its memes' scores (2 × upvotes − downvotes + reactions). Tap a team to see its memes.</p>
      {wars.data?.challenges?.length > 0 && (
        <section>
          <h2>Team challenges</h2>
          <div className="mz-contest-list">
            {wars.data.challenges.map((c) => (
              <Link key={c.id} to={`/meme-zone/contests/${c.id}`} className="mz-contest">
                <TeamCrest team={c.team} size={36} /><div><h3>{c.title}</h3></div><PhaseBadge phase={c.phase} />
              </Link>
            ))}
          </div>
        </section>
      )}
      {focus && (
        <section>
          <h2>{teams.find((t) => t.team_id === focus)?.name} memes</h2>
          <MemeGrid params={{ team: focus, sort: "top", period }} empty={<Empty>No memes for this team in this period.</Empty>} />
        </section>
      )}
    </div>
  );
}
