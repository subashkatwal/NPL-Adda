import { Crown, Medal } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import MemeCard from "../../components/MemeCard.jsx";
import { Empty, ErrorState, Loading, TeamCrest } from "../../components/ui.jsx";
import { useApi } from "../../lib/useApi.js";
import { PeriodTabs } from "./TeamWars.jsx";

export default function HallOfFame() {
  const [period, setPeriod] = useState("week");
  const hof = useApi(`/memelab/hall-of-fame?period=${period}`);
  const [memes, setMemes] = useState({});
  const data = hof.data;

  return (
    <div className="mz-hof">
      <div className="mz-toolbar"><PeriodTabs period={period} setPeriod={setPeriod} /></div>
      {hof.loading && <Loading />}
      {hof.error && <ErrorState>Rankings couldn't load.</ErrorState>}
      {data && (
        <>
          <p className="meta mz-rules">{data.label}. {data.scoring}</p>
          <div className="mz-hof-grid">
            <section>
              <h2><Crown size={20} aria-hidden /> Top creators</h2>
              {data.top_creators.length === 0 ? <Empty>No memes published in this period yet.</Empty> : (
                <ol className="ranking ranking-fans">
                  {data.top_creators.map((c) => (
                    <li key={c.fan_id}>
                      <span className="rank-num">{c.rank}</span>
                      <span className="rank-name">{c.nickname}</span>
                      <span className="rank-sub">{c.memes} {c.memes === 1 ? "meme" : "memes"} · <Link to={`/meme-zone/m/${c.best_meme}`}>best meme</Link></span>
                      <span className="rank-val">{c.score}<small> pts</small></span>
                    </li>
                  ))}
                </ol>
              )}
            </section>
            <section>
              <h2><Medal size={20} aria-hidden /> Team rankings</h2>
              <ol className="ranking">
                {data.teams.map((t) => (
                  <li key={t.team_id}>
                    <span className="rank-num">{t.rank}</span>
                    <TeamCrest team={t} size={30} />
                    <span className="rank-name">{t.name}</span>
                    <span className="rank-sub">{t.memes} memes</span>
                    <span className="rank-val">{t.score}</span>
                  </li>
                ))}
              </ol>
            </section>
          </div>
          {data.contest_winners.length > 0 && (
            <section>
              <h2>Meme of the Match winners</h2>
              <div className="mz-winners">
                {data.contest_winners.map((c) => (
                  <Link key={c.id} to={`/meme-zone/m/${c.winner.meme_id}`} className="mz-featured-item">
                    {c.winner.image_url ? <img src={c.winner.image_url} alt="" loading="lazy" /> : <span>{c.title}</span>}
                    <small>{c.winner.author} · {c.title}</small>
                  </Link>
                ))}
              </div>
            </section>
          )}
          <section>
            <h2>Most-voted memes</h2>
            {data.top_memes.length === 0 ? <Empty>Nothing yet for this period.</Empty> : (
              <div className="mz-grid">
                {data.top_memes.map((m, i) => (
                  <MemeCard key={m.id} meme={memes[m.id] ?? m} rank={i + 1}
                    onChange={(u) => setMemes((all) => ({ ...all, [u.id]: u }))} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
