import { CalendarClock, Check, Crown, Trophy } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { BackLink, Empty, ErrorState, Loading, Select, TeamCrest } from "../../components/ui.jsx";
import { results } from "../../lib/api.js";
import { useAuth } from "../../lib/authContext.js";
import { useFan } from "../../lib/fanContext.js";
import { useFeedback } from "../../lib/feedbackContext.js";
import { timeAgo } from "../../lib/format.js";
import { useApi } from "../../lib/useApi.js";
import { memeService } from "../../services/memelab.js";

const when = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kathmandu", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const PHASE = {
  upcoming: ["Opens soon", ""], submissions: ["Entries open", "is-live"], open: ["Entries & voting open", "is-live"],
  voting: ["Voting open", "is-live"], submissions_closed: ["Entries closed", ""], closed: ["Results pending", ""],
  finalized: ["Results final", "is-done"], cancelled: ["Cancelled", ""], draft: ["Draft", ""],
};

export function PhaseBadge({ phase }) {
  const [label, cls] = PHASE[phase] ?? [phase, ""];
  return <span className={`mz-phase ${cls}`}>{label}</span>;
}

function ContestCard({ contest }) {
  const m = contest.match;
  return (
    <Link to={`/meme-zone/contests/${contest.id}`} className="mz-contest">
      <div className="mz-contest-teams">
        {m ? (<><TeamCrest team={m.home} size={36} /><em>vs</em><TeamCrest team={m.away} size={36} /></>)
          : contest.team ? <TeamCrest team={contest.team} size={40} /> : <Trophy size={32} aria-hidden />}
      </div>
      <div>
        <h3>{contest.title}</h3>
        <p className="meta"><CalendarClock size={14} aria-hidden /> Voting until {when.format(new Date(contest.voting_close_at))} NPT
          · {contest.entry_count} {contest.entry_count === 1 ? "entry" : "entries"}</p>
      </div>
      <PhaseBadge phase={contest.phase} />
    </Link>
  );
}

export default function Contests() {
  const active = useApi("/memelab/contests?phase=active");
  const finished = useApi("/memelab/contests?phase=finished");
  return (
    <div className="mz-contests">
      <section>
        <h2>Live & upcoming</h2>
        {active.loading && <Loading />}
        {active.error && <ErrorState>Contests couldn't load.</ErrorState>}
        {active.data && results(active.data).length === 0 && <Empty>No contests are running right now. Staff open one per match.</Empty>}
        <div className="mz-contest-list">{results(active.data).map((c) => <ContestCard key={c.id} contest={c} />)}</div>
      </section>
      {results(finished.data).length > 0 && (
        <section>
          <h2>Finished</h2>
          <div className="mz-contest-list">{results(finished.data).map((c) => <ContestCard key={c.id} contest={c} />)}</div>
        </section>
      )}
    </div>
  );
}

export function ContestDetail() {
  const { contestId } = useParams();
  const { user, openAuth } = useAuth();
  const { profile } = useFan();
  const { notify, confirm } = useFeedback();
  const [contest, setContest] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => memeService.contest(contestId).then(setContest).catch(setError), [contestId]);
  useEffect(() => {
    load();
  }, [load]);
  const myMemes = useApi(profile ? `/memelab/memes?author=${profile.id}&sort=new` : null);
  const [pick, setPick] = useState("");

  if (error) return <ErrorState>{error.status === 404 ? "This contest doesn't exist." : "This contest couldn't load."}</ErrorState>;
  if (!contest) return <Loading />;
  const votingOpen = ["voting", "open"].includes(contest.phase);
  const entriesOpen = ["submissions", "open"].includes(contest.phase);
  const entered = new Set(contest.entries.map((e) => e.meme.id));
  const eligible = results(myMemes.data).filter((m) => !entered.has(m.id));

  async function act(fn, ok) {
    if (!user) return openAuth({ reason: "Log in to enter and vote." });
    setBusy(true);
    try {
      await fn();
      notify({ text: ok });
      await load();
    } catch (err) {
      const detail = err.data?.detail ?? err.data?.entry?.[0] ?? err.data?.post?.[0] ?? err.message;
      notify({ type: "error", text: detail });
    } finally {
      setBusy(false);
    }
  }

  const vote = async (entry) => {
    if (contest.my_vote && contest.my_vote !== entry.id) {
      if (!(await confirm({ title: "Move your vote?", message: "You have one vote per contest. It moves to this meme.", confirmLabel: "Move vote" }))) return;
    }
    act(() => memeService.contestVote(contest.id, entry.id), "Vote counted!");
  };

  return (
    <div className="mz-contest-detail">
      <BackLink fallback="/meme-zone/contests" label="Contests" />
      <header className="mz-contest-head">
        <div>
          <PhaseBadge phase={contest.phase} />
          <h2>{contest.title}</h2>
          {contest.match && (
            <p className="meta">{contest.match.label} · {when.format(new Date(contest.match.starts_at))} NPT · match status: {contest.match.status}
              {contest.match.result_text ? ` · ${contest.match.result_text}` : ""}</p>
          )}
          {contest.description && <p>{contest.description}</p>}
        </div>
        <dl className="mz-contest-times">
          <div><dt>Entries</dt><dd>{when.format(new Date(contest.submissions_open_at))} – {when.format(new Date(contest.submissions_close_at))}</dd></div>
          <div><dt>Voting</dt><dd>{when.format(new Date(contest.voting_open_at))} – {when.format(new Date(contest.voting_close_at))}</dd></div>
        </dl>
      </header>

      {contest.winner && (
        <div className="mz-winner">
          <Crown size={22} aria-hidden />
          <div><strong>Winner: {contest.winner.author}</strong><span>{contest.winner.votes} votes</span></div>
          <Link to={`/meme-zone/m/${contest.winner.meme_id}`} className="btn btn-sm">See the meme</Link>
        </div>
      )}

      {entriesOpen && (
        <div className="mz-enter">
          {!user ? <button type="button" className="btn btn-primary" onClick={() => openAuth()}>Log in to enter</button>
            : eligible.length === 0 ? (
              <p className="meta">Publish a meme about this match or its teams, then enter it here. <Link to="/meme-zone/create" className="text-link">Make one →</Link></p>
            ) : (
              <>
                <Select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Your meme">
                  <option value="">Choose one of your published memes…</option>
                  {eligible.map((m) => <option key={m.id} value={m.id}>{m.body.slice(0, 60)}</option>)}
                </Select>
                <button type="button" className="btn btn-primary" disabled={!pick || busy}
                  onClick={() => act(() => memeService.enter(contest.id, pick), contest.requires_entry_review ? "Entered - staff will review it." : "You're in! Good luck.")}>
                  <Trophy size={16} aria-hidden /> Enter
                </button>
              </>
            )}
        </div>
      )}

      <p className="meta mz-rules">{contest.rules}</p>
      {contest.entries.length === 0 ? <Empty>No entries yet{entriesOpen ? " - be the first!" : "."}</Empty> : (
        <ol className="mz-entries">
          {contest.entries.map((e, i) => (
            <li key={e.id} className={contest.my_vote === e.id ? "is-voted" : ""}>
              <span className="mz-entry-rank">{e.final_rank ?? i + 1}</span>
              <Link to={`/meme-zone/m/${e.meme.id}`} className="mz-entry-img">
                {e.meme.available && e.meme.image_url ? <img src={e.meme.image_url} alt={e.meme.body} loading="lazy" /> : <span>Meme removed</span>}
              </Link>
              <div className="mz-entry-info">
                <strong>{e.meme.author}</strong>
                <span>{e.meme.team ?? "Neutral"} · entered {timeAgo(e.created_at)}{e.status !== "approved" ? ` · ${e.status}` : ""}</span>
              </div>
              <strong className="mz-entry-votes">{e.votes}<small> votes</small></strong>
              {votingOpen && e.status === "approved" && !e.is_mine && (
                <button type="button" className={`btn btn-sm ${contest.my_vote === e.id ? "btn-primary" : ""}`} disabled={busy || contest.my_vote === e.id}
                  onClick={() => vote(e)}>{contest.my_vote === e.id ? <><Check size={14} aria-hidden /> Your vote</> : "Vote"}</button>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
