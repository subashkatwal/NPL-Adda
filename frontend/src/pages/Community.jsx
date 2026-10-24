import { useParams } from "react-router-dom";

import { BackLink, Empty, ErrorState, Loading } from "../components/ui.jsx";
import { results } from "../lib/api.js";
import { useApi } from "../lib/useApi.js";

export default function Community() {
  const { teamId } = useParams();
  const team = useApi(`/teams/${teamId}`);
  const posts = useApi(`/content?team=${teamId}`);

  return (
    <section className="page">
      <BackLink fallback="/home" />
      <p className="eyebrow">Team community</p>
      <h1>{team.data ? `${team.data.name} adda` : "Community"}</h1>
      {posts.loading && <Loading label="Loading posts" />}
      {posts.error && <ErrorState>Posts could not be loaded.</ErrorState>}
      {!posts.loading && !posts.error && results(posts.data).length === 0 && (
        <Empty>No published posts for this team yet. Posting opens in the next release.</Empty>
      )}
      <div className="post-grid">
        {results(posts.data).map((post) => (
          <article key={post.id} className="post-tile">
            <h3>{post.title || post.author_nickname}</h3>
            <p>{post.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
