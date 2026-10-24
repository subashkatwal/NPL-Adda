import { Loader2, PenSquare } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import MemeCard from "../../components/MemeCard.jsx";
import { Empty, ErrorState, Loading, Select } from "../../components/ui.jsx";
import { results } from "../../lib/api.js";
import { useApi } from "../../lib/useApi.js";
import { memeService } from "../../services/memelab.js";

const SORTS = { trending: "Trending", new: "Newest", top: "Top voted" };

/** Paged meme grid. `params` are API filters; changing them restarts from page 1. */
export function MemeGrid({ params, empty }) {
  const [state, setState] = useState({ items: [], next: false, page: 1, loading: true, error: null });
  const key = JSON.stringify(params);

  const load = useCallback(async (page) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await memeService.memes({ ...JSON.parse(key), page });
      setState((s) => ({ items: page === 1 ? data.results : [...s.items, ...data.results], next: Boolean(data.next),
        page, loading: false, error: null }));
    } catch (error) {
      setState((s) => ({ ...s, loading: false, error }));
    }
  }, [key]);

  useEffect(() => {
    load(1);
  }, [load]);

  const replace = (updated) => setState((s) => ({ ...s, items: s.items.map((m) => (m.id === updated.id ? updated : m)) }));

  if (state.error && !state.items.length) return <ErrorState>Memes couldn't load. Try again in a moment.</ErrorState>;
  if (state.loading && !state.items.length) return <Loading label="Loading memes" />;
  if (!state.items.length) return empty ?? <Empty>No memes here yet.</Empty>;
  return (
    <>
      <div className="mz-grid">
        {state.items.map((m) => <MemeCard key={m.id} meme={m} onChange={replace} />)}
      </div>
      {state.next && (
        <div className="mz-more">
          <button type="button" className="btn" disabled={state.loading} onClick={() => load(state.page + 1)}>
            {state.loading && <Loader2 className="spin" size={16} aria-hidden />} Load more memes
          </button>
        </div>
      )}
    </>
  );
}

export default function Feed() {
  const [params, setParams] = useSearchParams();
  const sort = params.get("sort") ?? "trending";
  const team = params.get("team") ?? "";
  const period = params.get("period") ?? "week";
  const teams = results(useApi("/teams").data);
  const set = (k, v) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };

  return (
    <>
      <FeaturedStrip />
      <div className="mz-toolbar">
        <div className="segmented" role="tablist" aria-label="Sort memes">
          {Object.entries(SORTS).map(([value, label]) => (
            <button key={value} role="tab" aria-selected={sort === value} onClick={() => set("sort", value === "trending" ? "" : value)}>
              {label}
            </button>
          ))}
        </div>
        {sort === "top" && (
          <Select value={period} onChange={(e) => set("period", e.target.value)} aria-label="Period">
            <option value="week">This week</option><option value="month">This month</option>
            <option value="season">This season</option><option value="all">All time</option>
          </Select>
        )}
        <Select value={team} onChange={(e) => set("team", e.target.value)} aria-label="Team">
          <option value="">All teams</option>
          {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </Select>
        <Link to="/meme-zone/create" className="btn btn-primary"><PenSquare size={16} aria-hidden /> Make a meme</Link>
      </div>
      <MemeGrid params={{ sort, team, period: sort === "top" ? period : undefined }}
        empty={<Empty>No memes yet{team ? " for this team" : ""}. <Link to="/meme-zone/create">Be the first to make one.</Link></Empty>} />
    </>
  );
}

function FeaturedStrip() {
  const featured = useApi("/memelab/memes?featured=true&sort=new");
  const items = results(featured.data).slice(0, 6);
  if (!items.length) return null;
  return (
    <section className="mz-featured" aria-label="Featured memes">
      <h2>Featured by the adda</h2>
      <div className="mz-featured-row">
        {items.map((m) => (
          <Link key={m.id} to={`/meme-zone/m/${m.id}`} className="mz-featured-item">
            {m.image_url ? <img src={m.image_url} alt={m.body} loading="lazy" /> : <span>{m.body}</span>}
            <small>{m.author.nickname}</small>
          </Link>
        ))}
      </div>
    </section>
  );
}
