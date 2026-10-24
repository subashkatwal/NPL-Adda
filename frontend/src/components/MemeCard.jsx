import { ArrowBigDown, ArrowBigUp, Flag, MessageCircle, Share2, Sparkles, Star } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../lib/authContext.js";
import { useFeedback } from "../lib/feedbackContext.js";
import { timeAgo } from "../lib/format.js";
import { REACTIONS, memeService } from "../services/memelab.js";
import MemeCanvas from "./MemeCanvas.jsx";
import { FanName, TeamCrest } from "./ui.jsx";

/** The meme picture: the server-rendered image, or a canvas render for memes made before server rendering. */
export function MemeImage({ meme, eager = false }) {
  const [broken, setBroken] = useState(false);
  if (meme.image_url && !broken) {
    return (
      <img className="mz-img" src={meme.image_url} alt={meme.body} loading={eager ? "eager" : "lazy"} decoding="async"
        width="1080" height="1080" onError={() => setBroken(true)} />
    );
  }
  if (meme.legacy) {
    return <MemeCanvas size={540} template={meme.legacy.template} caption={meme.legacy.caption} team={meme.team} />;
  }
  return <div className="mz-img mz-missing" role="img" aria-label="Image unavailable"><span>Image unavailable</span></div>;
}

/** Reactions, votes, comments, share and report for one meme. Server state is the source of truth. */
export function MemeActions({ meme, onChange, showComments = true }) {
  const { user, openAuth } = useAuth();
  const { notify, confirm } = useFeedback();
  const [busy, setBusy] = useState(false);
  const score = meme.counts.upvotes - meme.counts.downvotes;

  async function guard(fn) {
    if (!user) {
      openAuth({ reason: "Log in to react, vote and comment." });
      return;
    }
    if (meme.is_mine) {
      notify({ type: "error", text: "That's your own meme - let other fans judge it." });
      return;
    }
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      notify({ type: "error", text: err.status === 403 ? "Create your fan profile first (Choose a team)." : err.message });
    } finally {
      setBusy(false);
    }
  }

  const react = (kind) => guard(async () => onChange(await memeService.react(meme.id, kind)));
  const vote = (type) => guard(async () => {
    await (meme.my_vote === type ? memeService.unvote(meme.id) : memeService.vote(meme.id, type));
    onChange(await memeService.meme(meme.id));
  });

  async function share() {
    const url = `${window.location.origin}/meme-zone/m/${meme.id}`;
    try {
      if (navigator.share) await navigator.share({ title: "NPL Adda meme", text: meme.body, url });
      else {
        await navigator.clipboard.writeText(url);
        notify({ text: "Link copied." });
      }
    } catch (err) {
      if (err?.name !== "AbortError") notify({ type: "error", text: "Couldn't share. Copy the address bar instead." });
    }
  }

  const report = () => guard(async () => {
    if (!(await confirm({ title: "Report this meme?", message: "A moderator will review it.", confirmLabel: "Report", danger: true }))) return;
    await memeService.report(meme.id, "inappropriate");
    notify({ text: "Reported. Thanks for keeping the adda clean." });
  });

  return (
    <div className="mz-actions">
      <div className="mz-reactions" role="group" aria-label="Reactions">
        {REACTIONS.map((r) => (
          <button key={r.kind} type="button" className={`mz-react ${meme.my_reaction === r.kind ? "is-on" : ""}`}
            aria-pressed={meme.my_reaction === r.kind} aria-label={`${r.label} (${meme.counts.by_reaction[r.kind]})`}
            disabled={busy} onClick={() => react(r.kind)}>
            <span aria-hidden>{r.emoji}</span>{meme.counts.by_reaction[r.kind] > 0 && <b>{meme.counts.by_reaction[r.kind]}</b>}
          </button>
        ))}
      </div>
      <div className="mz-vote" role="group" aria-label="Vote">
        <button type="button" className={meme.my_vote === "up" ? "is-up" : ""} aria-pressed={meme.my_vote === "up"}
          aria-label="Upvote" disabled={busy} onClick={() => vote("up")}><ArrowBigUp size={20} aria-hidden /></button>
        <span className="mz-score">{score}</span>
        <button type="button" className={meme.my_vote === "down" ? "is-down" : ""} aria-pressed={meme.my_vote === "down"}
          aria-label="Downvote" disabled={busy} onClick={() => vote("down")}><ArrowBigDown size={20} aria-hidden /></button>
      </div>
      <div className="mz-tools">
        {showComments && (
          <Link to={`/meme-zone/m/${meme.id}#comments`} className="mz-tool" aria-label={`${meme.counts.comments} comments`}>
            <MessageCircle size={17} aria-hidden /> {meme.counts.comments}
          </Link>
        )}
        <button type="button" className="mz-tool" onClick={share} aria-label="Share"><Share2 size={17} aria-hidden /></button>
        {!meme.is_mine && (
          <button type="button" className="mz-tool" onClick={report} aria-label="Report"><Flag size={16} aria-hidden /></button>
        )}
      </div>
    </div>
  );
}

export default function MemeCard({ meme, onChange, rank }) {
  return (
    <article className={`mz-card ${meme.is_featured ? "is-featured" : ""}`}
      style={meme.team ? { "--team": meme.team.primary_color } : undefined}>
      <Link to={`/meme-zone/m/${meme.id}`} className="mz-card-media" aria-label={`Open meme: ${meme.body}`}>
        <MemeImage meme={meme} />
        {rank && <span className="mz-rank">#{rank}</span>}
        {meme.is_featured && <span className="mz-flag"><Star size={13} aria-hidden /> Featured</span>}
        {meme.is_ai_generated && <span className="mz-flag mz-ai"><Sparkles size={13} aria-hidden /> AI-assisted</span>}
      </Link>
      <header className="mz-card-head">
        {meme.team ? <TeamCrest team={meme.team} size={26} /> : <span className="mz-dot" aria-hidden />}
        <div>
          <FanName fan={meme.author} />
          <span>{meme.team?.short_name ?? "Neutral"} · {timeAgo(meme.published_at)}{meme.match ? ` · ${meme.match.label}` : ""}</span>
        </div>
      </header>
      <MemeActions meme={meme} onChange={onChange} />
    </article>
  );
}
