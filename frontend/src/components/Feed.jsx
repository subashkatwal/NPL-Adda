import { Flag, Send, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";

import { results } from "../lib/api.js";
import { matchDate } from "../lib/format.js";
import { useT } from "../lib/prefs.js";
import { useApi } from "../lib/useApi.js";
import { contentService } from "../services/content.js";
import MemeCanvas from "./MemeCanvas.jsx";
import { Empty, ErrorState, Loading } from "./ui.jsx";

export function Composer({ team }) {
  const t = useT();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [status, setStatus] = useState({ busy: false, error: null, sent: false });

  async function submit(event) {
    event.preventDefault();
    setStatus({ busy: true, error: null, sent: false });
    try {
      await contentService.create({ title: title.trim(), body: body.trim(), team: team.id });
      setTitle("");
      setBody("");
      setStatus({ busy: false, error: null, sent: true });
    } catch (error) {
      setStatus({ busy: false, error, sent: false });
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      <label className="sr-only" htmlFor="post-title">{t("feed.title")}</label>
      <input id="post-title" value={title} maxLength={150} placeholder={t("feed.title")} onChange={(e) => setTitle(e.target.value)} />
      <label className="sr-only" htmlFor="post-body">{t("feed.write", { team: team.name })}</label>
      <textarea id="post-body" value={body} required minLength={2} maxLength={5000} rows={3}
        placeholder={t("feed.write", { team: team.name })} onChange={(e) => setBody(e.target.value)} />
      <div className="composer-foot">
        {status.sent && <span className="meta" role="status">{t("feed.sent")}</span>}
        {status.error && <ErrorState error={status.error} />}
        <button className="btn btn-primary btn-sm" disabled={status.busy || body.trim().length < 2}>
          <Send size={15} aria-hidden /> {t("feed.submit")}
        </button>
      </div>
    </form>
  );
}

function PostItem({ post, teamsById, canInteract }) {
  const t = useT();
  const [score, setScore] = useState(post.score);
  const [note, setNote] = useState(null);
  const [error, setError] = useState(null);

  async function vote(type) {
    setError(null);
    try {
      await contentService.vote(post.id, type);
      setScore((await contentService.get(post.id)).score); // server-computed score, never a local guess
    } catch (err) {
      setError(err);
    }
  }

  async function report() {
    setError(null);
    try {
      await contentService.report(post.id, "inappropriate");
      setNote(t("feed.reported"));
    } catch (err) {
      setError(err);
    }
  }

  return (
    <article className={`post ${post.meme ? "post-meme" : ""}`}>
      <header>
        <strong>{post.author_nickname}</strong>
        <time dateTime={post.published_at}>{post.published_at ? matchDate(post.published_at) : ""}</time>
        {post.meme && <span className="chip">{t("feed.meme")}</span>}
      </header>
      {post.meme ? (
        <MemeCanvas size={540} template={post.meme.template} caption={post.meme.caption}
          team={teamsById[post.meme.team ?? post.team]} />
      ) : (
        <>
          {post.title && <h3>{post.title}</h3>}
          <p>{post.body}</p>
        </>
      )}
      <footer>
        <div className="vote-group" aria-label="Votes">
          <button className="icon-btn" disabled={!canInteract} onClick={() => vote("up")} aria-label={t("feed.up")}>
            <ThumbsUp size={15} aria-hidden />
          </button>
          <span className="score-num">{score}</span>
          <button className="icon-btn" disabled={!canInteract} onClick={() => vote("down")} aria-label={t("feed.down")}>
            <ThumbsDown size={15} aria-hidden />
          </button>
        </div>
        {canInteract && !note && (
          <button className="link-btn" onClick={report}><Flag size={13} aria-hidden /> {t("feed.report")}</button>
        )}
        {note && <span className="meta">{note}</span>}
      </footer>
      {error && <ErrorState error={error} />}
    </article>
  );
}

/** Published posts for a team (or all teams). Unapproved and removed posts never come back from the API. */
export function PostFeed({ teamId, teamsById, canInteract }) {
  const t = useT();
  const feed = useApi(`/content${teamId ? `?team=${teamId}` : ""}`);
  if (feed.loading) return <Loading />;
  if (feed.error) return <ErrorState>{t("state.unavailable")}</ErrorState>;
  const posts = results(feed.data);
  if (!posts.length) return <Empty>{t("feed.empty")}</Empty>;
  return (
    <div className="feed">
      {posts.map((p) => <PostItem key={p.id} post={p} teamsById={teamsById} canInteract={canInteract} />)}
    </div>
  );
}
