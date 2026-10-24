import { Check, Lock, Trophy } from "lucide-react";
import { useState } from "react";

import { ACTIVITY_LABELS, PERSONALITY_LABELS } from "../i18n/strings.js";
import { matchDate, matchTime } from "../lib/format.js";
import { usePrefs, useT } from "../lib/prefs.js";
import { useApi } from "../lib/useApi.js";
import { fanService } from "../services/fan.js";
import { Empty, ErrorState, FanName, TeamCrest } from "./ui.jsx";

const when = (iso) => `${matchDate(iso)} ${matchTime(iso)}`;

/** Six balls of an over as a progress meter: filled = done. Targets above 6 are scaled to 6 balls. */
export function OverDots({ current, target }) {
  const balls = 6;
  const filled = Math.round((Math.min(current, target) / target) * balls);
  return (
    <span className="over-dots" role="img" aria-label={`${current} of ${target}`}>
      {Array.from({ length: balls }, (_, i) => <i key={i} className={i < filled ? "on" : ""} />)}
    </span>
  );
}

/** Poll card. Shows counts only when the API includes `results` (its visibility rule allows it). */
export function PollCard({ poll: initial, canVote }) {
  const t = useT();
  const [poll, setPoll] = useState(initial);
  const [choice, setChoice] = useState(initial.my_vote);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const voted = Boolean(poll.my_vote);
  const results = poll.results;
  const counts = Object.fromEntries((results?.options ?? []).map((o) => [o.id, o.votes]));

  async function vote() {
    setBusy(true);
    setError(null);
    try {
      await fanService.vote(poll.id, choice);
      setPoll(await fanService.poll(poll.id));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="poll">
      <header>
        <h3>{poll.question}</h3>
        <span className="meta">
          {poll.is_accepting_votes ? t("polls.closes", { when: when(poll.closes_at) }) : t("polls.closed")}
        </span>
      </header>
      <ul>
        {poll.options.map((o) => {
          const share = results?.total_votes ? Math.round((counts[o.id] / results.total_votes) * 100) : 0;
          return (
            <li key={o.id}>
              <label className={`poll-option ${choice === o.id ? "is-chosen" : ""}`}>
                {!voted && poll.is_accepting_votes && canVote && (
                  <input type="radio" name={`poll-${poll.id}`} checked={choice === o.id} onChange={() => setChoice(o.id)} />
                )}
                <span className="poll-text">{o.text}{poll.my_vote === o.id && <Check size={14} aria-label={t("polls.voted")} />}</span>
                {results && <span className="poll-pct">{share}%</span>}
                {results && <span className="poll-bar" style={{ "--share": `${share}%` }} aria-hidden />}
              </label>
            </li>
          );
        })}
      </ul>
      <footer>
        {results ? (
          <span className="meta">{t("polls.votes", { n: results.total_votes })}</span>
        ) : (
          <span className="meta"><Lock size={12} aria-hidden /> {t(poll.results_visibility === "after_close" ? "polls.hiddenClose" : "polls.hidden")}</span>
        )}
        {!voted && poll.is_accepting_votes && canVote && (
          <button className="btn btn-primary btn-sm" disabled={!choice || busy} onClick={vote}>{t("polls.vote")}</button>
        )}
      </footer>
      {error && <ErrorState error={error} />}
    </article>
  );
}

/** Winner prediction for one scheduled match. The server enforces the deadline and one pick per fan. */
export function PredictionCard({ match, existing, canPredict }) {
  const t = useT();
  const [pick, setPick] = useState(existing?.predicted_winner ?? null);
  const [saved, setSaved] = useState(existing ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const teams = [match.home_team_detail, match.away_team_detail];
  const savedTeam = teams.find((x) => x.id === saved?.predicted_winner);

  async function lockIn() {
    setBusy(true);
    setError(null);
    try {
      setSaved(await fanService.predict(match.id, pick));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="prediction">
      <header>
        <span className="meta">{t("pred.deadline", { when: when(match.starts_at) })}</span>
        <span className="meta">{match.venue}</span>
      </header>
      <div className="prediction-teams" role="radiogroup" aria-label={t("pred.pick")}>
        {teams.map((team, i) => (
          <button key={team.id} type="button" role="radio" aria-checked={pick === team.id}
            className={`prediction-team ${pick === team.id ? "is-picked" : ""}`} style={{ "--team": team.primary_color }}
            disabled={!canPredict} onClick={() => setPick(team.id)}>
            <TeamCrest team={team} size={40} />
            <span>{team.name}</span>
            {i === 0 && <em className="vs" aria-hidden>vs</em>}
          </button>
        ))}
      </div>
      <footer>
        {savedTeam ? <span className="meta"><Check size={13} aria-hidden /> {t("pred.locked", { team: savedTeam.name })}</span>
          : <span className="meta">{t("pred.free")}</span>}
        {canPredict && (
          <button className="btn btn-primary btn-sm" disabled={!pick || busy || pick === saved?.predicted_winner}
            onClick={lockIn}>{saved ? t("pred.change") : t("pred.save")}</button>
        )}
      </footer>
      {error && <ErrorState error={error} />}
    </article>
  );
}

export function TeamRanking({ rows, highlight }) {
  const t = useT();
  if (!rows.length || rows.every((r) => r.points === 0 && r.members === 0)) return <Empty>{t("rank.empty")}</Empty>;
  const max = Math.max(...rows.map((r) => r.points), 1);
  return (
    <ol className="ranking">
      {rows.map((r) => (
        <li key={r.team.id} className={r.team.id === highlight ? "is-me" : ""} style={{ "--team": r.team.primary_color }}>
          <span className="rank-num">{r.rank}</span>
          <TeamCrest team={r.team} size={30} />
          <span className="rank-name">{r.team.name}</span>
          <span className="rank-bar" style={{ "--share": `${(r.points / max) * 100}%` }} aria-hidden />
          <span className="rank-val">{r.points}<small> {t("rank.points")}</small></span>
          <span className="rank-sub">{r.members} {t("rank.members")}</span>
        </li>
      ))}
    </ol>
  );
}

export function FanRanking({ rows, meId }) {
  const t = useT();
  const { lang } = usePrefs();
  if (!rows.length || rows.every((r) => r.points === 0)) return <Empty>{t("rank.empty")}</Empty>;
  return (
    <ol className="ranking ranking-fans">
      {rows.map((r) => (
        <li key={r.id} className={r.id === meId ? "is-me" : ""}>
          <span className="rank-num">{r.rank}</span>
          <span className="rank-name"><FanName fan={r} bold={false} /></span>
          <span className="rank-sub">{PERSONALITY_LABELS[lang][r.fan_personality]}</span>
          <span className="rank-val">{r.points}<small> {t("rank.points")}</small></span>
        </li>
      ))}
    </ol>
  );
}

export function ChallengeRail({ challenges }) {
  return (
    <ul className="challenges">
      {challenges.map((c) => (
        <li key={c.badge.id} className={c.completed ? "is-done" : ""}>
          <Trophy size={18} aria-hidden />
          <div>
            <strong>{c.badge.name}</strong>
            <span>{c.badge.description}</span>
          </div>
          <OverDots current={c.current} target={c.target} />
          <span className="challenge-count">{c.current}/{c.target}</span>
        </li>
      ))}
    </ul>
  );
}

export function ActivityList({ items }) {
  const t = useT();
  const { lang } = usePrefs();
  if (!items.length) return <Empty>{t("me.noHistory")}</Empty>;
  return (
    <ol className="activity">
      {items.map((a) => (
        <li key={a.id}>
          <time dateTime={a.occurred_at}>{matchDate(a.occurred_at)}</time>
          <span>{ACTIVITY_LABELS[lang][a.activity_type] ?? a.activity_type}</span>
          <span className={`delta ${a.points_delta > 0 ? "pos" : a.points_delta < 0 ? "neg" : ""}`}>
            {a.points_delta > 0 ? `+${a.points_delta}` : a.points_delta || "·"}
          </span>
        </li>
      ))}
    </ol>
  );
}

export function StatStrip({ stats }) {
  return (
    <dl className="stat-strip">
      {stats.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value ?? "–"}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Loads the prediction split; the API refuses (403) until predictions close, which we show as-is. */
export function PredictionSplit({ matchId }) {
  const t = useT();
  const { data, error } = useApi(`/fanpage/matches/${matchId}/prediction-summary`);
  if (error?.status === 403) return <span className="meta">{t("pred.splitHidden")}</span>;
  if (!data) return null;
  return (
    <div className="split">
      <span className="meta">{t("pred.split")}</span>
      {data.split.map((s) => (
        <span key={s.team}>{s.name}: <b>{s.count}</b></span>
      ))}
    </div>
  );
}
