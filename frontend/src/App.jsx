import { Navigate, Route, Routes } from "react-router-dom";

import { Footer, Header } from "./components/ui.jsx";
import { useFan } from "./lib/fanContext.js";
import AdminApp from "./pages/admin/AdminApp.jsx";
import ChooseTeam from "./pages/ChooseTeam.jsx";
import Community from "./pages/Community.jsx";
import FanCard from "./pages/FanCard.jsx";
import FanWars from "./pages/FanWars.jsx";
import Landing from "./pages/Landing.jsx";
import MatchDetail from "./pages/MatchDetail.jsx";
import Matches from "./pages/Matches.jsx";
import MemeZone from "./pages/memezone/MemeZone.jsx";
import NotFound from "./pages/NotFound.jsx";
import Profile from "./pages/Profile.jsx";
import PublicFanCard from "./pages/PublicFanCard.jsx";
import Settings from "./pages/Settings.jsx";
import TeamHome from "./pages/TeamHome.jsx";

export default function App() {
  const { profile } = useFan();
  return (
    <>
      <Header profile={profile} />
      <main>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/choose-team" element={<ChooseTeam />} />
          <Route path="/home" element={<TeamHome />} />
          <Route path="/fan-wars" element={<FanWars />} />
          <Route path="/meme-zone/*" element={<MemeZone />} />
          <Route path="/meme-lab" element={<Navigate to="/meme-zone" replace />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/card" element={<FanCard />} />
          <Route path="/fans/:profileId" element={<PublicFanCard />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/teams/:teamId/community" element={<Community />} />
          <Route path="/matches" element={<Matches />} />
          <Route path="/matches/:matchId" element={<MatchDetail />} />
          <Route path="/staff/*" element={<AdminApp />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <Footer />
    </>
  );
}
