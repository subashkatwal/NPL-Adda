/**
 * The NPL Adda fan card. Every value comes from the server's card payload (GET /fanpage/me/card
 * or /fanpage/<id>/card); `draft` overlays unsaved edits for the live preview.
 * Three editions: classic (Himalaya ridges), stadium (floodlights over the pitch), matchday (crimson).
 */
import { Flame, MessageCircle, Shield, Star, Trophy } from "lucide-react";
import { forwardRef } from "react";

import { LogoMark, PersonaPill, TeamCrest } from "./ui.jsx";

import { BADGE_ICONS } from "../lib/badgeIcons.js";

const FOOTERS = {
  classic: "One game · One community · NPL Adda",
  stadium: "Cricket brings us together",
  matchday: "Support · Cheer · Repeat",
};

/** Nepal's flag: two stacked pennants, crimson with a blue border, white moon and sun. */
export function NepalFlag({ className = "" }) {
  return (
    <svg className={className} viewBox="0 0 40 50" aria-label="Nepal flag" role="img">
      <path d="M2 2 L36 22 H14 L36 48 H2 Z" fill="#003893" />
      <path d="M5 7.5 L27 19.5 H8.5 L28 45 H5 Z" fill="#DC143C" />
      <path d="M8.5 13 a5 5 0 0 0 9 0 a4.4 3.6 0 0 1 -9 0 Z" fill="#fff" />
      <circle cx="13" cy="15" r="1.6" fill="#fff" />
      <circle cx="13" cy="35" r="4" fill="#fff" />
    </svg>
  );
}

function Backdrop({ theme }) {
  if (theme === "stadium") {
    return (
      <div className="fc-bg" aria-hidden>
        <i className="fc-light fc-light-l" />
        <i className="fc-light fc-light-r" />
        <svg className="fc-stands" viewBox="0 0 300 120" preserveAspectRatio="none">
          <path d="M0 70 Q150 20 300 70 V120 H0 Z" fill="rgb(255 255 255 / 0.05)" />
          <path d="M0 92 Q150 52 300 92 V120 H0 Z" fill="rgb(255 255 255 / 0.04)" />
        </svg>
        <i className="fc-pitch" />
      </div>
    );
  }
  if (theme === "matchday") {
    return (
      <div className="fc-bg" aria-hidden>
        <svg className="fc-strokes" viewBox="0 0 300 420" preserveAspectRatio="none">
          <path d="M-20 120 L180 20 L210 40 L0 160 Z" fill="rgb(0 56 147 / 0.55)" />
          <path d="M120 420 L320 230 L330 270 L170 420 Z" fill="rgb(0 56 147 / 0.5)" />
          <path d="M-10 300 L140 200 L150 214 L0 322 Z" fill="rgb(255 255 255 / 0.08)" />
          <path d="M200 120 L320 60 L320 84 L214 140 Z" fill="rgb(255 255 255 / 0.1)" />
        </svg>
        <NepalFlag className="fc-flag-bg" />
      </div>
    );
  }
  return (
    <div className="fc-bg" aria-hidden>
      <svg className="fc-mountains" viewBox="0 0 300 160" preserveAspectRatio="none">
        <path d="M0 160 V96 L40 60 L66 82 L104 30 L140 72 L170 48 L214 98 L248 64 L300 104 V160 Z" fill="#141c31" />
        <path d="M104 30 L92 48 L104 44 L114 52 L120 44 Z M248 64 L238 76 L250 74 L258 80 Z M40 60 L32 70 L44 68 Z"
          fill="rgb(245 247 250 / 0.55)" />
        <path d="M0 160 V122 L56 92 L96 116 L150 84 L196 118 L246 96 L300 126 V160 Z" fill="#0f162a" />
      </svg>
      <i className="fc-slash fc-slash-tl" />
      <i className="fc-slash fc-slash-br" />
    </div>
  );
}

function Initials({ name }) {
  const letters = name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  return <span className="fc-initials">{letters || "?"}</span>;
}

const FanCardFace = forwardRef(function FanCardFace({ card, draft = {}, interactive = false }, ref) {
  const theme = draft.theme ?? card.theme;
  const nickname = (draft.nickname ?? card.nickname) || "Your name";
  const tagline = draft.tagline ?? card.tagline;
  const team = draft.team !== undefined ? draft.team : card.team;
  const avatar = draft.avatarUrl !== undefined ? draft.avatarUrl : card.avatar_url;
  const show = { avatar: true, stats: true, badges: true, since: true, ...(draft.privacy ?? {}) };
  const stats = show.stats ? card.stats : null;
  const badges = show.badges ? card.badges ?? [] : [];
  const season = card.season ?? new Date().getFullYear();

  function tilt(event) {
    if (!interactive || event.pointerType !== "mouse") return;
    const r = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty("--rx", `${((event.clientY - r.top) / r.height - 0.5) * -8}deg`);
    event.currentTarget.style.setProperty("--ry", `${((event.clientX - r.left) / r.width - 0.5) * 10}deg`);
    event.currentTarget.style.setProperty("--gx", `${((event.clientX - r.left) / r.width) * 100}%`);
  }
  function untilt(event) {
    event.currentTarget.style.setProperty("--rx", "0deg");
    event.currentTarget.style.setProperty("--ry", "0deg");
  }

  return (
    <article ref={ref} className={`fc fc-${theme} ${interactive ? "is-interactive" : ""}`}
      style={{ "--team": team?.primary_color ?? "#2b3a63", "--team-2": team?.secondary_color ?? "#c8ff4d" }}
      onPointerMove={tilt} onPointerLeave={untilt} aria-label={`${nickname}'s NPL Adda fan card`}>
      <Backdrop theme={theme} />
      <i className="fc-sheen" aria-hidden />

      <header className="fc-top">
        <span className="fc-logo"><LogoMark /><small>Cricket · Fans · Community</small></span>
        <span className="fc-edition">
          <b>{theme === "matchday" ? "Matchday Edition" : "Fan Card"}</b>
          <small>{theme === "matchday" ? `#NPL${season}` : `Season ${season}`}</small>
        </span>
      </header>

      <div className="fc-portrait">
        <div className="fc-ring">
          {show.avatar && avatar ? <img src={avatar} alt="" crossOrigin="anonymous" /> : <Initials name={nickname} />}
        </div>
        <NepalFlag className="fc-flag" />
      </div>

      <h3 className="fc-name">{nickname}</h3>
      {tagline && <p className="fc-tagline">{tagline}</p>}
      <PersonaPill personality={draft.personality ?? card.fan_personality} />

      <div className="fc-id">
        <div className="fc-crest">{team ? <TeamCrest team={team} size={46} /> : <Shield size={30} aria-hidden />}</div>
        <dl>
          <div className="fc-team"><dt>My team</dt><dd>{team?.name ?? "No team yet"}</dd></div>
          <div><dt>Fan ID</dt><dd className="fc-mono">{card.fan_code}</dd></div>
          {show.since && card.member_since && <div className="fc-since"><dt>Since</dt><dd>{card.member_since}</dd></div>}
        </dl>
      </div>

      {stats && (
        <dl className="fc-stats">
          <div><dt><Flame size={15} aria-hidden /> <b>{stats.memes}</b></dt><dd>Memes</dd></div>
          <div><dt><MessageCircle size={15} aria-hidden /> <b>{stats.comments}</b></dt><dd>Comments</dd></div>
          <div><dt><Star size={15} aria-hidden /> <b>{stats.points}</b></dt><dd>Points</dd></div>
        </dl>
      )}

      {badges.length > 0 && (
        <ul className="fc-badges" aria-label="Badges">
          {badges.slice(0, 5).map((b) => {
            const Icon = BADGE_ICONS[b.icon_name] ?? Trophy;
            return <li key={b.code} title={b.name}><Icon size={13} aria-hidden /></li>;
          })}
        </ul>
      )}

      <footer className="fc-foot">{FOOTERS[theme] ?? FOOTERS.classic}</footer>
    </article>
  );
});

export default FanCardFace;
