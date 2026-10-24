import { useState } from "react";

import FixtureCalendar from "../components/FixtureCalendar.jsx";
import { BackLink, Empty, ErrorState, Loading, MatchRow } from "../components/ui.jsx";
import { results } from "../lib/api.js";
import { useT } from "../lib/prefs.js";
import { useApi } from "../lib/useApi.js";

const FILTERS = { scheduled: "Fixtures", completed: "Results", "": "All" };

function MatchList({ status }) {
  const matches = useApi(`/matches?ordering=${status === "completed" ? "-starts_at" : "starts_at"}${status ? `&status=${status}` : ""}`);
  if (matches.loading) return <Loading label="Loading matches" />;
  if (matches.error) return <ErrorState>Match data is unavailable right now.</ErrorState>;
  if (results(matches.data).length === 0) {
    return <Empty>No matches on record for this view. Scores appear only once stored from a source.</Empty>;
  }
  return <div className="match-list">{results(matches.data).map((m) => <MatchRow key={m.id} match={m} />)}</div>;
}

export default function Matches() {
  const t = useT();
  const [status, setStatus] = useState("scheduled");

  return (
    <section className="page">
      <BackLink fallback="/" />
      <p className="eyebrow">Fixtures & results</p>
      <h1>{t("nav.matches")}</h1>
      <div className="segmented" role="tablist">
        {Object.entries(FILTERS).map(([value, label]) => (
          <button key={label} role="tab" aria-selected={status === value} onClick={() => setStatus(value)}>{label}</button>
        ))}
      </div>
      {status === "scheduled" ? <FixtureCalendar /> : <MatchList status={status} />}
    </section>
  );
}
