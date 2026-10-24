import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import FixtureCalendar from "../components/FixtureCalendar.jsx";

const json = (body) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const team = (id, name, short) => ({ id, name, short_name: short, primary_color: "#112233", secondary_color: "#ffeeaa" });
const LUL = team("lul", "Lumbini Lions", "LUL");
const SPR = team("spr", "Sudurpaschim Royals", "SPR");
const BRK = team("brk", "Biratnagar Kings", "BRK");
const CHR = team("chr", "Chitwan Rhinos", "CHR");
const match = (id, n, startsAt, home, away) => ({
  id, match_number: n, starts_at: startsAt, status: "scheduled", innings: [], winner: null,
  home_team: home.id, away_team: away.id, home_team_detail: home, away_team_detail: away,
});
const SEASONS = [
  { id: "dev", name: "Dev", year: 2099, source_metadata: { source: "development-sample" } },
  { id: "s26", name: "NPL 2026", year: 2026, starts_at: "2026-10-26", ends_at: "2026-11-21",
    source_metadata: { source: "published-schedule", venue: "TU International Cricket Ground, Kirtipur", revised: "2026-10-20",
      playoffs: [{ stage: "Final", starts_at: "2026-11-21T10:45:00+00:00", description: "Winner of Q1 v winner of Q2" }] } },
];
const MATCHES = [
  match("m1", 1, "2026-10-26T11:15:00+00:00", LUL, SPR), // 17:00 NPT
  match("m2", 2, "2026-10-27T06:45:00+00:00", BRK, CHR), // 12:30 NPT
];

afterEach(() => vi.restoreAllMocks());

describe("fixture calendar", () => {
  it("shows the published season by day, in Nepal time, with playoffs as TBD", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-22T06:00:00Z"));
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
      if (url.endsWith("/matches/seasons")) return json({ count: 2, next: null, results: SEASONS });
      if (url.includes("/matches?season=s26")) return json({ count: 2, next: null, results: MATCHES });
      return json({});
    });
    render(<MemoryRouter><FixtureCalendar /></MemoryRouter>);

    expect(await screen.findByText("NPL 2026 fixtures")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => url.includes("season=dev"))).toBe(false);
    // first match day is selected: the opener at 17:00 NPT, a day/night game, with a countdown
    const opener = screen.getByRole("link", { name: /Lumbini Lions/ });
    expect(within(opener).getByText("17:00")).toBeInTheDocument();
    expect(within(opener).getByText("D/N")).toBeInTheDocument();
    expect(within(opener).getByText(/in 4d/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Next match day/ }));
    expect(within(screen.getByRole("link", { name: /Biratnagar Kings/ })).getByText("12:30")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Full schedule/ }));
    expect(screen.getByText("Final")).toBeInTheDocument();
    expect(screen.getByText("Winner of Q1 v winner of Q2")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /vs|Lions|Kings/ })).toHaveLength(2);
    vi.useRealTimers();
  });
});
