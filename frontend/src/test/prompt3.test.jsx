import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PollCard } from "../components/engage.jsx";
import { PrefToggles } from "../components/ui.jsx";
import { wrapLines } from "../lib/memeRender.js";
import { translate } from "../lib/prefs.js";
import { PrefsProvider } from "../lib/PrefsProvider.jsx";

const json = (status, body) => Promise.resolve(new Response(JSON.stringify(body), { status }));

describe("preferences", () => {
  it("toggles theme and language, persists them and reflects them on <html>", () => {
    render(<PrefsProvider><PrefToggles /></PrefsProvider>);
    const start = document.documentElement.dataset.theme;
    fireEvent.click(screen.getByRole("button", { name: /theme/i }));
    expect(document.documentElement.dataset.theme).not.toBe(start);
    expect(localStorage.getItem("npl-adda.theme")).toBe(document.documentElement.dataset.theme);

    fireEvent.click(screen.getByRole("button", { name: "Switch to Nepali" }));
    expect(document.documentElement.lang).toBe("ne");
    expect(localStorage.getItem("npl-adda.lang")).toBe("ne");
    expect(screen.getByRole("button", { name: "Switch to English" })).toBeInTheDocument();
  });

  it("translates with placeholders and falls back to English", () => {
    expect(translate("ne", "choose.welcome", { team: "CHR" })).toBe("CHR अड्डामा स्वागत छ।");
    expect(translate("ne", "missing.key")).toBe("missing.key");
    expect(translate("en", "polls.votes", { n: 3 })).toBe("3 votes");
  });
});

describe("PollCard", () => {
  const poll = {
    id: "p1", question: "Best finisher?", options: [{ id: "a", text: "A" }, { id: "b", text: "B" }],
    is_accepting_votes: true, closes_at: new Date(Date.now() + 3600e3).toISOString(),
    results_visibility: "after_vote", my_vote: null, results: null,
  };

  it("shows counts only once the API returns results", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((url, init = {}) => {
      if (url.endsWith("/vote") && init.method === "POST") return json(201, {});
      return json(200, { ...poll, my_vote: "b", results: { poll: "p1", total_votes: 4, options: [{ id: "a", votes: 1 }, { id: "b", votes: 3 }] } });
    });
    render(<PollCard poll={poll} canVote />);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    expect(screen.getByText("Results appear after you vote.")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("radio")[1]);
    fireEvent.click(screen.getByRole("button", { name: "Vote" }));
    expect(await screen.findByText("75%")).toBeInTheDocument();
    expect(screen.getByText("4 votes")).toBeInTheDocument();
  });

  it("surfaces an API rejection instead of faking success", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(409, { poll: ["You have already voted in this poll."] }));
    render(<PollCard poll={poll} canVote />);
    fireEvent.click(screen.getAllByRole("radio")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Vote" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already voted");
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });
});

describe("wrapLines", () => {
  const measure = (s) => s.length * 10;
  it("wraps words and splits over-long words", () => {
    expect(wrapLines(measure, "last ball six for the win", 100)).toEqual(["last ball", "six for", "the win"]);
    expect(wrapLines(measure, "supercalifragilistic", 50)).toEqual(["super", "calif", "ragil", "istic"]);
  });
});
