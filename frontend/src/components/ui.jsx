import {
  AlertTriangle, ArrowLeft, CalendarDays, ChevronDown, Database, Eye, EyeOff, House, Languages, Laugh, Loader2, LogIn,
  Moon, Shield, Sun, Swords,
} from "lucide-react";
import { useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";

import { PERSONALITY_LABELS } from "../i18n/strings.js";
import { useAuth } from "../lib/authContext.js";
import { isDevSample, matchDate, matchTime, timeAgo } from "../lib/format.js";
import { usePrefs, useT } from "../lib/prefs.js";
import UserMenu from "./UserMenu.jsx";

/** NPL Adda wordmark (transparent PNG made from public/"npl adda.png"); white parts, so it sits on dark. */
export function LogoMark({ className = "" }) {
  return <img className={`logo-mark ${className}`} src="/brand/npl-adda-logo.png" alt="NPL Adda" width="517" height="168" />;
}

export function Logo() {
  return (
    <Link to="/" className="logo" aria-label="NPL Adda home">
      <LogoMark className="logo-on-dark" />
      <img className="logo-mark logo-on-light" src="/brand/npl-adda-logo-light.png" alt="" width="517" height="168" />
    </Link>
  );
}

export function PrefToggles() {
  const { lang, setLang, theme, setTheme } = usePrefs();
  const t = useT();
  return (
    <div className="toggles">
      <button type="button" className="icon-btn lang-btn" onClick={() => setLang(lang === "en" ? "ne" : "en")}
        aria-label={t("toggle.lang.label")} title={t("toggle.lang.label")}>
        <Languages size={16} aria-hidden /> <span>{t("toggle.lang")}</span>
      </button>
      <button type="button" className="icon-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        aria-label={t(theme === "dark" ? "toggle.theme.light" : "toggle.theme.dark")}
        title={t(theme === "dark" ? "toggle.theme.light" : "toggle.theme.dark")}>
        {theme === "dark" ? <Sun size={17} aria-hidden /> : <Moon size={17} aria-hidden />}
      </button>
    </div>
  );
}

/** Top nav on wide screens; on phones the same links move to a bottom tab bar (see .tabbar). */
export function Header({ profile }) {
  const t = useT();
  const links = [
    { to: "/matches", key: "nav.matches", icon: CalendarDays },
    { to: "/fan-wars", key: "nav.fanWars", icon: Swords },
    { to: "/meme-zone", key: "nav.memeLab", icon: Laugh },
    ...(profile?.current_team ? [{ to: "/home", key: "nav.myTeam", icon: Shield }] : []),
  ];
  return (
    <>
      <header className="site-header">
        <Logo />
        <nav aria-label="Main" className="top-nav">
          {links.map((link) => <NavLink key={link.to} to={link.to}>{t(link.key)}</NavLink>)}
        </nav>
        <PrefToggles />
        <UserMenu />
      </header>
      {/* Outside the header: its backdrop-filter would trap a fixed child. */}
      <nav aria-label="Main" className="tabbar">
        <NavLink to="/" end><House size={21} aria-hidden /><span>{t("nav.home")}</span></NavLink>
        {links.map((link) => (
          <NavLink key={link.to} to={link.to}><link.icon size={21} aria-hidden /><span>{t(link.key)}</span></NavLink>
        ))}
      </nav>
    </>
  );
}

/** Original monogram crest built from the team's short name and stored colours; not an official logo. */
export function TeamCrest({ team, size = 56 }) {
  return (
    <svg className="crest" width={size} height={size} viewBox="0 0 56 56" role="img" aria-label={`${team.name} crest`}>
      <path d="M28 2 L52 10 V28 C52 42 41 50 28 54 C15 50 4 42 4 28 V10 Z" fill={team.primary_color} />
      <path d="M28 8 L46 14 V28 C46 38 38 44 28 47 C18 44 10 38 10 28 V14 Z" fill="none"
        stroke={team.secondary_color} strokeWidth="2" />
      <text x="28" y="33" textAnchor="middle" fill={team.secondary_color}>{team.short_name}</text>
    </svg>
  );
}

/** The fan type the fan chose (Die-hard, Analyst, ...), as a coloured pill. */
export function PersonaPill({ personality, chip = false }) {
  const { lang } = usePrefs();
  if (!personality) return null;
  const label = personality === "die_hard" && lang === "en" ? "Die-hard fan" : PERSONALITY_LABELS[lang][personality];
  return <span className={`${chip ? "fan-chip" : "fc-level"} fc-persona-${personality}`}>{label}</span>;
}

/** Compact fan identity: nickname (linked to their public card when public) + fan type. */
export function FanName({ fan, bold = true }) {
  if (!fan) return null;
  const text = bold ? <strong>{fan.nickname}</strong> : <span>{fan.nickname}</span>;
  const name = fan.is_public === false ? text : <Link className="fan-name" to={`/fans/${fan.id}`}>{text}</Link>;
  return (
    <span className="fan-ident">
      {name}
      <PersonaPill personality={fan.personality ?? fan.fan_personality} chip />
    </span>
  );
}

export function Loading({ label }) {
  const t = useT();
  return (
    <p className="state" role="status">
      <Loader2 className="spin" size={18} aria-hidden /> {label ?? t("state.loading")}…
    </p>
  );
}

export function ErrorState({ error, children }) {
  const t = useT();
  return (
    <p className="state state-error" role="alert">
      <AlertTriangle size={18} aria-hidden /> {children || error?.message || t("state.error")}
    </p>
  );
}

export function Empty({ children }) {
  return <p className="state state-empty">{children}</p>;
}

/** Native <select> with a themed chevron, so every dropdown looks and aligns the same. */
export function Select({ className = "", children, ...props }) {
  return (
    <span className={`select ${className}`}>
      <select {...props}>{children}</select>
      <ChevronDown className="select-icon" size={18} aria-hidden />
    </span>
  );
}

/** Password field with an eye button that shows or hides what was typed. */
export function PasswordInput({ className = "", ...props }) {
  const t = useT();
  const [visible, setVisible] = useState(false);
  const label = t(visible ? "auth.hidePassword" : "auth.showPassword");
  return (
    <span className={`password-input ${className}`}>
      <input {...props} type={visible ? "text" : "password"} />
      <button type="button" className="password-eye" onClick={() => setVisible((v) => !v)}
        aria-label={label} title={label} aria-pressed={visible}>
        {visible ? <EyeOff size={18} aria-hidden /> : <Eye size={18} aria-hidden />}
      </button>
    </span>
  );
}

/** Back link: returns to the previous page, or to `fallback` when the page was opened directly. */
export function BackLink({ fallback = "/", label }) {
  const navigate = useNavigate();
  const location = useLocation();
  const t = useT();
  const hasHistory = location.key !== "default";
  return (
    <a
      href={fallback}
      className="back-link"
      onClick={(event) => {
        event.preventDefault();
        if (hasHistory) navigate(-1);
        else navigate(fallback);
      }}
    >
      <ArrowLeft size={18} aria-hidden /> {label ?? t("nav.back")}
    </a>
  );
}

/** Numbered section heading, e.g. "01 Polls". */
export function SectionHead({ index, title, aside }) {
  return (
    <div className="section-head">
      {index && <span className="section-index">{String(index).padStart(2, "0")}</span>}
      <h2>{title}</h2>
      {aside && <div className="section-aside">{aside}</div>}
    </div>
  );
}

/** Where the match data came from and how fresh it is; development samples are labelled loudly. */
export function SourceTag({ match }) {
  if (isDevSample(match)) {
    return <span className="tag tag-dev"><Database size={13} aria-hidden /> Development sample · not a real result</span>;
  }
  const fresh = timeAgo(match.last_synced_at);
  return (
    <span className="tag">
      <Database size={13} aria-hidden /> Source: {match.data_source}
      {fresh ? ` · updated ${fresh}` : " · freshness unknown"}
    </span>
  );
}

export function MatchRow({ match }) {
  const home = match.home_team_detail;
  const away = match.away_team_detail;
  const innings = match.innings || [];
  return (
    <Link to={`/matches/${match.id}`} className="match-row">
      <div className="match-when">
        <span>{matchDate(match.starts_at)}</span>
        <span>{matchTime(match.starts_at)}</span>
      </div>
      <div className="match-teams">
        {[home, away].map((team) => {
          const inn = innings.find((i) => i.batting_team === team.id);
          return (
            <div key={team.id} className={match.winner === team.id ? "is-winner" : ""}>
              <TeamCrest team={team} size={28} />
              <span className="team-name">{team.name}</span>
              <span className="score">
                {inn ? `${inn.runs}/${inn.wickets}` : ""}
                {inn && <small> ({inn.overs})</small>}
              </span>
            </div>
          );
        })}
      </div>
      <div className="match-meta">
        <span className={`status status-${match.status}`}>{match.status}</span>
        {match.result_text && <span className="result">{match.result_text}</span>}
        <SourceTag match={match} />
      </div>
    </Link>
  );
}

/** Inline "log in to take part" prompt for guests browsing a page with protected actions. */
export function LoginPrompt({ message }) {
  const t = useT();
  const { openAuth } = useAuth();
  return (
    <div className="login-prompt">
      <LogIn size={18} aria-hidden />
      <span>{message ?? t("auth.required")}</span>
      <button type="button" className="btn btn-primary btn-sm" onClick={() => openAuth()}>{t("auth.login")}</button>
    </div>
  );
}

export function Footer() {
  const t = useT();
  return (
    <footer className="site-footer">
      <p className="disclaimer">{t("footer.disclaimer")}</p>
      <p className="credit">
        Hero photo: Tribhuvan University International Cricket Stadium by{" "}
        <a href="https://commons.wikimedia.org/wiki/File:Tribhuvan_University_International_Cricket_Stadium.jpg"
          target="_blank" rel="noreferrer">Janak Bhatta</a>,{" "}
        <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noreferrer">CC BY-SA 4.0</a>,
        resized.
      </p>
    </footer>
  );
}
