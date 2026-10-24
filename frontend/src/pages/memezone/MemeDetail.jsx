import { CornerDownRight, Download, Flag, Send, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { MemeActions, MemeImage } from "../../components/MemeCard.jsx";
import { BackLink, Empty, ErrorState, FanName, Loading, TeamCrest } from "../../components/ui.jsx";
import { useAuth } from "../../lib/authContext.js";
import { useFeedback } from "../../lib/feedbackContext.js";
import { timeAgo } from "../../lib/format.js";
import { memeService } from "../../services/memelab.js";

function Comment({ comment, onReply, onChanged }) {
  const { notify, confirm } = useFeedback();
  const { user } = useAuth();

  async function remove() {
    if (!(await confirm({ title: "Delete your comment?", confirmLabel: "Delete", danger: true }))) return;
    try {
      await memeService.deleteComment(comment.id);
      notify({ text: "Comment deleted." });
      onChanged();
    } catch (err) {
      notify({ type: "error", text: err.message });
    }
  }

  async function report() {
    if (!(await confirm({ title: "Report this comment?", message: "A moderator will review it.", confirmLabel: "Report", danger: true }))) return;
    try {
      await memeService.reportComment(comment.id, "inappropriate");
      notify({ text: "Reported. Thanks." });
    } catch (err) {
      notify({ type: "error", text: err.message });
    }
  }

  return (
    <li className="mz-comment">
      <div className="mz-comment-head">
        <FanName fan={comment.author} />
        <time dateTime={comment.created_at}>{timeAgo(comment.created_at)}</time>
      </div>
      {comment.is_hidden ? <p className="muted"><em>Hidden by a moderator.</em></p> : <p>{comment.body}</p>}
      {user && !comment.is_hidden && (
        <div className="mz-comment-tools">
          {onReply && <button type="button" className="link-btn" onClick={() => onReply(comment)}><CornerDownRight size={13} aria-hidden /> Reply</button>}
          {comment.is_mine
            ? <button type="button" className="link-btn" onClick={remove}><Trash2 size={13} aria-hidden /> Delete</button>
            : <button type="button" className="link-btn" onClick={report}><Flag size={13} aria-hidden /> Report</button>}
        </div>
      )}
      {comment.replies?.length > 0 && (
        <ul className="mz-replies">
          {comment.replies.map((r) => <Comment key={r.id} comment={r} onChanged={onChanged} />)}
        </ul>
      )}
    </li>
  );
}

function Comments({ memeId, onCount }) {
  const { user, openAuth } = useAuth();
  const { notify } = useFeedback();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [body, setBody] = useState("");
  const [replyTo, setReplyTo] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    memeService.comments(memeId).then(setData).catch(setError);
  }, [memeId]);
  useEffect(load, [load]);

  async function submit(e) {
    e.preventDefault();
    if (!user) return openAuth({ reason: "Log in to join the conversation." });
    if (!body.trim()) return notify({ type: "error", text: "Write something first." });
    setBusy(true);
    try {
      await memeService.comment(memeId, body.trim(), replyTo?.id ?? null);
      setBody("");
      setReplyTo(null);
      notify({ text: "Comment posted." });
      load();
      onCount?.();
    } catch (err) {
      notify({ type: "error", text: err.data?.body?.[0] ?? err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mz-comments" id="comments" aria-label="Comments">
      <h2>Comments {data ? <small>{data.count}</small> : null}</h2>
      <form className="mz-comment-form" onSubmit={submit} noValidate>
        {replyTo && (
          <p className="meta">Replying to {replyTo.author.nickname} · <button type="button" className="link-btn" onClick={() => setReplyTo(null)}>cancel</button></p>
        )}
        <label className="sr-only" htmlFor="comment-body">Comment</label>
        <textarea id="comment-body" rows={2} maxLength={1000} value={body} onChange={(e) => setBody(e.target.value)}
          placeholder={user ? "Add to the banter (English, नेपाली or Romanized)…" : "Log in to comment"} />
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy}><Send size={15} aria-hidden /> Post</button>
      </form>
      {error && <ErrorState>Comments couldn't load.</ErrorState>}
      {!data && !error && <Loading />}
      {data && data.results.length === 0 && <Empty>No comments yet. Start the adda.</Empty>}
      {data && (
        <ul className="mz-comment-list">
          {data.results.map((c) => <Comment key={c.id} comment={c} onReply={setReplyTo} onChanged={load} />)}
        </ul>
      )}
    </section>
  );
}

export default function MemeDetail() {
  const { memeId } = useParams();
  const [meme, setMeme] = useState(null);
  const [error, setError] = useState(null);
  const refresh = useCallback(() => memeService.meme(memeId).then(setMeme).catch(setError), [memeId]);
  useEffect(() => {
    setMeme(null);
    refresh();
  }, [refresh]);

  if (error) return <ErrorState>{error.status === 404 ? "This meme was removed or doesn't exist." : "This meme couldn't load."}</ErrorState>;
  if (!meme) return <Loading />;
  return (
    <div className="mz-detail">
      <BackLink fallback="/meme-zone" label="Meme Zone" />
      <div className="mz-detail-grid">
        <figure className="mz-detail-media" style={meme.team ? { "--team": meme.team.primary_color } : undefined}>
          <MemeImage meme={meme} eager />
        </figure>
        <div className="mz-detail-side">
          <header className="mz-card-head">
            {meme.team && <TeamCrest team={meme.team} size={34} />}
            <div>
              <strong>{meme.author.nickname}</strong>
              <span>{meme.team?.name ?? "Neutral"} · {timeAgo(meme.published_at)}</span>
            </div>
          </header>
          <p className="mz-caption" lang={meme.language === "ne" ? "ne" : undefined}>{meme.body}</p>
          {meme.match && <p className="meta">About {meme.match.label}</p>}
          {meme.is_ai_generated && <p className="meta">Captions suggested by AI and edited by the creator.</p>}
          <MemeActions meme={meme} onChange={setMeme} showComments={false} />
          {meme.image_url && (
            <a className="btn btn-sm" href={meme.image_url} download><Download size={15} aria-hidden /> Download</a>
          )}
          <Link to="/meme-zone/create" className="text-link">Make your own →</Link>
        </div>
      </div>
      <Comments memeId={meme.id} onCount={refresh} />
    </div>
  );
}
