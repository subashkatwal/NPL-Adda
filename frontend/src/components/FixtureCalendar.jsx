import { CalendarDays, ChevronLeft, ChevronRight, Clock, List, MapPin, Moon, Trophy } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api, results } from "../lib/api.js";
import { Empty, ErrorState, Loading, TeamCrest } from "./ui.jsx";

const TZ = "Asia/Kathmandu"; // fixtures are published in Nepal time
const DEV_SOURCE = "development-sample";
const fmt = (options) => new Intl.DateTimeFormat("en-GB", { timeZone: TZ, ...options });
const dayKeyFmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const timeFmt = fmt({ hour: "2-digit", minute: "2-digit", hour12: false });
const hourFmt = fmt({ hour: "numeric", hour12: false });
const weekdayFmt = fmt({ weekday: "short" });
const dayNumFmt = fmt({ day: "numeric" });
const monthFmt = fmt({ month: "short" });
const longDayFmt = fmt({ weekday: "long", day: "numeric", month: "long" });
const rangeFmt = fmt({ day: "numeric", month: "short", year: "numeric" });

const dayKey = (iso) => dayKeyFmt.format(new Date(iso));

/** Follow DRF pagination so a whole season (30+ fixtures) arrives in one list. */
async function fetchAll(path) {
  const rows = [];
  let next = path;
  while (next) {
    const page = await api(next);
    rows.push(...results(page));
    next = page?.next ? new URL(page.next).pathname.replace(/^.*\/api\/v1/, "") + new URL(page.next).search : null;
  }
  return rows;
}

/** The season to show: the nearest real (non-sample) season that hasn't finished, else the latest real one. */
function pickSeason(seasons) {
  const real = seasons.filter((s) => s.source_metadata?.source !== DEV_SOURCE);
  const today = dayKeyFmt.format(new Date());
  const live = real.filter((s) => !s.ends_at || s.ends_at >= today).sort((a, b) => a.year - b.year);
  return live[0] ?? real.sort((a, b) => b.year - a.year)[0] ?? null;
}

function countdown(iso, now) {
  const minutes = Math.round((new Date(iso).getTime() - now) / 60000);
  if (minutes <= 0) return null;
  const d = Math.floor(minutes / 1440);
  const h = Math.floor((minutes % 1440) / 60);
  const m = minutes % 60;
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function StatusBadge({ match, now }) {
  if (match.status === "live") return <span className="fx-badge fx-live"><i aria-hidden /> Live</span>;
  if (match.status === "completed") return <span className="fx-badge">Result</span>;
  if (match.status === "abandoned" || match.status === "postponed") {
    return <span className="fx-badge fx-warn">{match.status}</span>;
  }
  const left = countdown(match.starts_at, now);
  return left
    ? <span className="fx-badge fx-soon"><Clock size={13} aria-hidden /> in {left}</span>
    : <span className="fx-badge">Starting</span>;
}

function TimeBlock({ iso }) {
  const evening = Number(hourFmt.format(new Date(iso))) >= 16;
  return (
    <div className="fx-time">
      <strong>{timeFmt.format(new Date(iso))}</strong>
      <span>NPT</span>
      {evening && <span className="fx-dn" title="Day/night match"><Moon size={11} aria-hidden /> D/N</span>}
    </div>
  );
}

function FixtureCard({ match, now }) {
  const home = match.home_team_detail;
  const away = match.away_team_detail;
  const innings = match.innings ?? [];
  const score = (team) => {
    const inn = innings.find((i) => i.batting_team === team.id);
    return inn ? `${inn.runs}/${inn.wickets}` : null;
  };
  return (
    <Link to={`/matches/${match.id}`} className={`fx-card fx-${match.status}`}
      style={{ "--home": home.primary_color, "--away": away.primary_color }}>
      <TimeBlock iso={match.starts_at} />
      <div className="fx-teams">
        {[home, away].map((team, i) => (
          <div key={team.id} className={`fx-team ${match.winner === team.id ? "is-winner" : ""}`}>
            <TeamCrest team={team} size={40} />
            <span className="fx-name">{team.name}</span>
            <span className="fx-short">{team.short_name}</span>
            {score(team) && <span className="fx-score">{score(team)}</span>}
            {i === 0 && <em className="fx-vs" aria-hidden>vs</em>}
          </div>
        ))}
      </div>
      <div className="fx-meta">
        <StatusBadge match={match} now={now} />
        <span>Match {match.match_number ?? "—"}</span>
        {match.result_text && <span className="fx-result">{match.result_text}</span>}
      </div>
    </Link>
  );
}

function PlayoffCard({ playoff }) {
  return (
    <div className="fx-card fx-playoff">
      <TimeBlock iso={playoff.starts_at} />
      <div className="fx-teams">
        <p className="fx-stage"><Trophy size={15} aria-hidden /> {playoff.stage}</p>
        <p className="fx-tbd">TBD <em>vs</em> TBD</p>
        <p className="fx-desc">{playoff.description}</p>
      </div>
      <div className="fx-meta"><span className="fx-badge">Playoff</span></div>
    </div>
  );
}

function DayBlock({ day, now }) {
  return (
    <section className="fx-day" id={`fx-${day.key}`} aria-label={day.label}>
      <h3>
        {day.label}
        {day.isToday && <span className="fx-today-tag">Today</span>}
        <small>{day.items.length} {day.items.length === 1 ? "match" : "matches"}</small>
      </h3>
      <div className="fx-cards">
        {day.items.map((item) => (item.playoff
          ? <PlayoffCard key={item.playoff.stage} playoff={item.playoff} />
          : <FixtureCard key={item.match.id} match={item.match} now={now} />))}
      </div>
    </section>
  );
}

/** yosintv-style fixture calendar: a scrollable date strip with match counts, then that day's (or every) fixture. */
export default function FixtureCalendar() {
  const [state, setState] = useState({ loading: true, error: null, season: null, matches: [] });
  const [selected, setSelected] = useState(null);
  const [view, setView] = useState("day");
  const [now, setNow] = useState(() => Date.now());
  const strip = useRef(null);

  useEffect(() => {
    let live = true;
    (async () => {
      const season = pickSeason(results(await api("/matches/seasons")));
      if (!season) return { season: null, matches: [] };
      return { season, matches: await fetchAll(`/matches?season=${season.id}&ordering=starts_at`) };
    })()
      .then((data) => live && setState({ loading: false, error: null, ...data }))
      .catch((error) => live && setState({ loading: false, error, season: null, matches: [] }));
    const timer = setInterval(() => setNow(Date.now()), 30000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);

  const days = useMemo(() => {
    const byDay = new Map();
    const add = (iso, item) => {
      const key = dayKey(iso);
      if (!byDay.has(key)) byDay.set(key, { key, date: new Date(iso), items: [] });
      byDay.get(key).items.push({ iso, ...item });
    };
    state.matches.forEach((match) => add(match.starts_at, { match }));
    const taken = new Set(state.matches.map((m) => new Date(m.starts_at).getTime()));
    (state.season?.source_metadata?.playoffs ?? [])
      .filter((p) => !taken.has(new Date(p.starts_at).getTime())) // hidden once the real match is added
      .forEach((playoff) => add(playoff.starts_at, { playoff }));
    const today = dayKeyFmt.format(new Date(now));
    return [...byDay.values()]
      .sort((a, b) => a.key.localeCompare(b.key))
      .map((d) => ({
        ...d,
        items: d.items.sort((a, b) => a.iso.localeCompare(b.iso)),
        label: longDayFmt.format(d.date),
        isToday: d.key === today,
        isPast: d.key < today,
      }));
  }, [state.matches, state.season, now]);

  const active = selected ?? (days.find((d) => !d.isPast) ?? days[days.length - 1])?.key;

  useEffect(() => {
    strip.current?.querySelector(`[data-day="${active}"]`)?.scrollIntoView?.({ block: "nearest", inline: "center" });
  }, [active, days.length]);

  if (state.loading) return <Loading label="Loading fixtures" />;
  if (state.error) return <ErrorState>Fixtures are unavailable right now.</ErrorState>;
  if (!state.season || days.length === 0) return <Empty>No fixtures have been published yet.</Empty>;

  const { season } = state;
  const meta = season.source_metadata ?? {};
  const index = days.findIndex((d) => d.key === active);
  const current = days[index];
  const scrollStrip = (dir) => strip.current?.scrollBy({ left: dir * 280, behavior: "smooth" });

  return (
    <div className="fx">
      <header className="fx-head">
        <div>
          <h2>{season.name} fixtures</h2>
          <p className="meta">
            <CalendarDays size={15} aria-hidden />
            {season.starts_at && season.ends_at
              ? `${rangeFmt.format(new Date(season.starts_at))} – ${rangeFmt.format(new Date(season.ends_at))}`
              : season.year}
            {" · "}{state.matches.length + (meta.playoffs?.length ?? 0)} matches
            {meta.venue && <><span aria-hidden> · </span><MapPin size={15} aria-hidden /> {meta.venue}</>}
          </p>
        </div>
        <div className="segmented fx-views" role="tablist" aria-label="Fixture view">
          <button role="tab" aria-selected={view === "day"} onClick={() => setView("day")}>
            <CalendarDays size={15} aria-hidden /> By day
          </button>
          <button role="tab" aria-selected={view === "all"} onClick={() => setView("all")}>
            <List size={15} aria-hidden /> Full schedule
          </button>
        </div>
      </header>

      {view === "day" && (
        <>
          <div className="fx-strip-wrap">
            <button type="button" className="icon-btn fx-arrow" aria-label="Earlier dates" onClick={() => scrollStrip(-1)}>
              <ChevronLeft size={18} aria-hidden />
            </button>
            <div className="fx-strip" ref={strip} role="tablist" aria-label="Match days">
              {days.map((d) => (
                <button key={d.key} type="button" role="tab" data-day={d.key} aria-selected={d.key === active}
                  className={`fx-date ${d.isPast ? "is-past" : ""} ${d.isToday ? "is-today" : ""}`}
                  onClick={() => setSelected(d.key)}>
                  <span className="fx-wd">{d.isToday ? "Today" : weekdayFmt.format(d.date)}</span>
                  <strong>{dayNumFmt.format(d.date)}</strong>
                  <span className="fx-mo">{monthFmt.format(d.date)}</span>
                  <span className="fx-dots" aria-label={`${d.items.length} matches`}>
                    {d.items.map((item, i) => <i key={i} className={item.playoff ? "is-playoff" : ""} />)}
                  </span>
                </button>
              ))}
            </div>
            <button type="button" className="icon-btn fx-arrow" aria-label="Later dates" onClick={() => scrollStrip(1)}>
              <ChevronRight size={18} aria-hidden />
            </button>
          </div>

          {current && <DayBlock day={current} now={now} />}
          <div className="fx-pager">
            <button type="button" className="btn btn-sm" disabled={index <= 0} onClick={() => setSelected(days[index - 1].key)}>
              <ChevronLeft size={16} aria-hidden /> Previous match day
            </button>
            <button type="button" className="btn btn-sm" disabled={index >= days.length - 1}
              onClick={() => setSelected(days[index + 1].key)}>
              Next match day <ChevronRight size={16} aria-hidden />
            </button>
          </div>
        </>
      )}

      {view === "all" && days.map((d) => <DayBlock key={d.key} day={d} now={now} />)}

      <p className="fx-source">
        Times are Nepal time (NPT, UTC+5:45). Schedule as published{meta.revised ? `, revised ${meta.revised}` : ""}
        {meta.source_url && <> · <a href={meta.source_url} target="_blank" rel="noreferrer">source</a></>}.
      </p>
    </div>
  );
}
