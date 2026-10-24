import { Lock, Pencil } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import FanCardFace from "../components/FanCardFace.jsx";
import { BackLink, ErrorState, Loading, PersonaPill } from "../components/ui.jsx";
import { fanService } from "../services/fan.js";

/** Another fan's card at /fans/:profileId — only what that fan chose to show. */
export default function PublicFanCard() {
  const { profileId } = useParams();
  const [state, setState] = useState({ card: null, error: null });

  useEffect(() => {
    let live = true;
    setState({ card: null, error: null });
    fanService.publicCard(profileId)
      .then((card) => live && setState({ card, error: null }))
      .catch((error) => live && setState({ card: null, error }));
    return () => { live = false; };
  }, [profileId]);

  const { card, error } = state;
  return (
    <section className="page fc-page fc-public">
      <BackLink fallback="/fan-wars" />
      {error?.status === 404 ? (
        <div className="fc-private">
          <Lock size={28} aria-hidden />
          <h1>Card not available</h1>
          <p className="lede">This fan card is private or no longer exists.</p>
        </div>
      ) : error ? (
        <ErrorState error={error} />
      ) : !card ? (
        <Loading label="Loading fan card" />
      ) : (
        <div className="fc-public-grid">
          <div className="fc-stage"><FanCardFace card={card} draft={{ privacy: card.privacy }} interactive /></div>
          <div className="fc-public-side">
            <p className="eyebrow">{card.team?.name ?? "NPL Adda"} fan</p>
            <h1>{card.nickname}</h1>
            {card.tagline && <p className="lede">{card.tagline}</p>}
            <p><PersonaPill personality={card.fan_personality} /></p>
            {card.is_owner
              ? <Link className="btn btn-primary" to="/card"><Pencil size={16} aria-hidden /> Edit my card</Link>
              : <Link className="btn btn-primary" to="/card">Make your own fan card</Link>}
            <p className="meta">An independent digital fan identity. Not official team or league membership.</p>
          </div>
        </div>
      )}
    </section>
  );
}
