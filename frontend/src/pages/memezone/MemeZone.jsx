import { Flame, PenSquare, Swords, Trophy, Medal } from "lucide-react";
import { NavLink, Route, Routes } from "react-router-dom";

import { useT } from "../../lib/prefs.js";
import Contests, { ContestDetail } from "./Contests.jsx";
import Create from "./Create.jsx";
import Feed from "./Feed.jsx";
import HallOfFame from "./HallOfFame.jsx";
import MemeDetail from "./MemeDetail.jsx";
import TeamWars from "./TeamWars.jsx";

const TABS = [
  { to: "/meme-zone", end: true, icon: Flame, label: "Trending" },
  { to: "/meme-zone/team-wars", icon: Swords, label: "Team Wars" },
  { to: "/meme-zone/create", icon: PenSquare, label: "Meme Lab" },
  { to: "/meme-zone/contests", icon: Trophy, label: "Meme of the Match" },
  { to: "/meme-zone/hall-of-fame", icon: Medal, label: "Hall of Fame" },
];

/** Meme Zone hub: feed, team wars, the creator, contests and rankings under one roof. */
export default function MemeZone() {
  const t = useT();
  return (
    <div className="mz">
      <header className="mz-hero">
        <p className="eyebrow">NPL ADDA</p>
        <h1>{t("meme.title")}</h1>
        <p className="lede">Make memes, back your team, win Meme of the Match.</p>
        <nav className="mz-tabs" aria-label="Meme Zone">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return <NavLink key={tab.to} to={tab.to} end={tab.end}><Icon size={17} aria-hidden /> {tab.label}</NavLink>;
          })}
        </nav>
      </header>
      <div className="mz-body">
        <Routes>
          <Route index element={<Feed />} />
          <Route path="team-wars" element={<TeamWars />} />
          <Route path="create" element={<Create />} />
          <Route path="contests" element={<Contests />} />
          <Route path="contests/:contestId" element={<ContestDetail />} />
          <Route path="hall-of-fame" element={<HallOfFame />} />
          <Route path="m/:memeId" element={<MemeDetail />} />
        </Routes>
      </div>
    </div>
  );
}
