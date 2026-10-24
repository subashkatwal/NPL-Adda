import { useParams } from "react-router-dom";

import { BackLink, Empty, ErrorState, Loading, MatchRow, SourceTag } from "../components/ui.jsx";
import { useApi } from "../lib/useApi.js";

export default function MatchDetail() {
  const { matchId } = useParams();
  const match = useApi(`/matches/${matchId}`);
  const stats = useApi(`/matches/${matchId}/performances`);

  if (match.loading) return <section className="page"><Loading /></section>;
  if (match.error) return <section className="page"><ErrorState>This match could not be found.</ErrorState></section>;

  const m = match.data;
  const teamName = (id) => (id === m.home_team_detail.id ? m.home_team_detail.name : m.away_team_detail.name);

  return (
    <section className="page">
      <BackLink fallback="/matches" />
      <p className="eyebrow">{m.venue}</p>
      <h1>{m.home_team_detail.name} vs {m.away_team_detail.name}</h1>
      <MatchRow match={m} />
      <SourceTag match={m} />

      <h2>Innings</h2>
      {m.innings.length === 0 && <Empty>No scores recorded yet.</Empty>}
      {m.innings.length > 0 && (
        <table className="table">
          <thead><tr><th>Innings</th><th>Batting</th><th>Score</th><th>Overs</th><th>Run rate</th><th>Extras</th></tr></thead>
          <tbody>
            {m.innings.map((i) => (
              <tr key={i.id}>
                <td>{i.innings_number}</td><td>{teamName(i.batting_team)}</td><td>{i.runs}/{i.wickets}</td>
                <td>{i.overs}</td><td>{i.run_rate ?? "–"}</td><td>{i.extras}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Player statistics</h2>
      {!stats.loading && (stats.data ?? []).length === 0 && <Empty>Player statistics are not available for this match.</Empty>}
      {(stats.data ?? []).length > 0 && (
        <table className="table">
          <thead><tr><th>Player</th><th>R</th><th>B</th><th>SR</th><th>W</th><th>Econ</th></tr></thead>
          <tbody>
            {stats.data.map((p) => (
              <tr key={p.id}>
                <td>{p.player_name}</td><td>{p.runs_scored}{p.is_not_out ? "*" : ""}</td><td>{p.balls_faced}</td>
                <td>{p.strike_rate ?? "–"}</td><td>{p.wickets_taken}</td><td>{p.economy ?? "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
