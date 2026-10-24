import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FeedbackProvider } from "../components/Feedback.jsx";
import { AuthContext } from "../lib/authContext.js";
import { FanContext } from "../lib/fanContext.js";
import MemeZone from "../pages/memezone/MemeZone.jsx";

const json = (status, body) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const TEAM = { id: "t1", name: "Chitwan Rhinos", short_name: "CHR", city: "Chitwan", primary_color: "#2F5D50", secondary_color: "#F2A541" };
const TEMPLATE = { id: "tp", name: "Scoreboard Shout", slug: "scoreboard-shout", layout_config: { background: "scoreboard" } };
const MEME = {
  id: "m1", image_url: "/media/memes/rendered/m1.jpg", body: "Rain again / every season", language: "en",
  author: { id: "f2", nickname: "Rhino Roar" }, team: TEAM, match: null, legacy: null, engagement: 3,
  counts: { upvotes: 1, downvotes: 0, reactions: 1, comments: 2, by_reaction: { fire: 1, laugh: 0, clap: 0, heartbreak: 0 } },
  my_vote: null, my_reaction: null, is_mine: false, is_featured: false, is_ai_generated: false,
  published_at: new Date().toISOString(),
};

function renderAt(path, fetchImpl, { user = { id: "u1", email: "f@x.np" }, profile = { id: "f1", nickname: "Fan", current_team: TEAM } } = {}) {
  vi.spyOn(globalThis, "fetch").mockImplementation((url, init = {}) => fetchImpl(url, init) ?? json(404, {}));
  render(
    <MemoryRouter initialEntries={[path]}>
      <FeedbackProvider>
        <AuthContext.Provider value={{ user, status: "ready", openAuth: vi.fn() }}>
          <FanContext.Provider value={{ profile: user ? profile : null, status: "ready", refresh: vi.fn(), setProfile: vi.fn() }}>
            <Routes><Route path="/meme-zone/*" element={<MemeZone />} /></Routes>
          </FanContext.Provider>
        </AuthContext.Provider>
      </FeedbackProvider>
    </MemoryRouter>,
  );
}

const base = (url) => {
  if (url.includes("/teams")) return json(200, { count: 1, results: [TEAM] });
  if (url.includes("/memelab/templates")) return json(200, { count: 1, results: [TEMPLATE] });
  if (url.includes("/memelab/caption-status")) return json(200, { provider: "mock", model: "", ai: false });
  if (url.includes("/memelab/drafts") && !url.includes("/submit")) return json(200, { count: 0, results: [] });
  if (url.includes("/matches")) return json(200, { count: 0, results: [] });
  if (url.includes("/memelab/render")) return Promise.resolve(new Response(new Blob(["jpg"], { type: "image/jpeg" }), { status: 200 }));
  return null;
};

beforeEach(() => {
  document.cookie = "csrftoken=t";
  globalThis.URL.createObjectURL = vi.fn(() => "blob:preview");
  globalThis.URL.revokeObjectURL = vi.fn();
});
afterEach(() => vi.restoreAllMocks());

describe("Meme Zone", () => {
  it("shows the feed to guests and toggles a reaction for fans", async () => {
    let reacted = null;
    renderAt("/meme-zone", (url, init) => {
      if (url.includes("/memes/m1/react")) {
        reacted = JSON.parse(init.body).kind;
        return json(200, { ...MEME, my_reaction: "laugh", counts: { ...MEME.counts, reactions: 2, by_reaction: { ...MEME.counts.by_reaction, laugh: 1 } } });
      }
      if (url.includes("/memelab/memes")) return json(200, { count: 1, next: null, results: url.includes("featured") ? [] : [MEME] });
      return base(url);
    });
    expect(await screen.findByRole("img", { name: MEME.body })).toHaveAttribute("src", MEME.image_url);
    fireEvent.click(screen.getByRole("button", { name: /^Laugh/ }));
    expect(await screen.findByRole("button", { name: "Laugh (1)" })).toHaveAttribute("aria-pressed", "true");
    expect(reacted).toBe("laugh");
  });

  it("labels template captions honestly and puts a picked option into the editor", async () => {
    let body;
    renderAt("/meme-zone/create", (url, init) => {
      if (url.endsWith("/memelab/generations")) {
        body = JSON.parse(init.body);
        return json(201, {
          request: { id: "r1", status: "completed", provider: "mock" }, is_mock: true, provider: "mock", verified_facts: false,
          notice: "Captions from the offline templates (fixed lines filled with stored facts), not an AI model.",
          captions: ["One / Two", "Three / Four"], options: [{ top: "One", bottom: "Two" }, { top: "Three", bottom: "Four" }],
          draft: { id: "d1" },
        });
      }
      return base(url);
    });
    expect(await screen.findByText(/offline caption templates/)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("e.g. rain before the final over"), { target: { value: "rain delay" } });
    fireEvent.click(screen.getByRole("radio", { name: "Rivalry" }));
    fireEvent.click(screen.getByRole("button", { name: /Suggest 3 captions/ }));
    expect(await screen.findByText(/not an AI model/)).toBeInTheDocument();
    expect(screen.getByText(/No verified match data used/)).toBeInTheDocument();
    expect(body).toMatchObject({ topic: "rain delay", style: "rivalry", language: "en", team: "t1" });
    expect(body.idempotency_key).toBeTruthy();
    expect(screen.getByLabelText("Top text")).toHaveValue("One");
    fireEvent.click(screen.getByRole("button", { name: /Three/ }));
    expect(screen.getByLabelText("Bottom text")).toHaveValue("Four");
  });

  it("checks captions in the page and explains duplicate memes on publish", async () => {
    renderAt("/meme-zone/create", (url, init) => {
      if (url.endsWith("/memelab/drafts") && init.method === "POST") return json(201, { id: "d9", status: "draft" });
      if (url.endsWith("/drafts/d9/submit")) return json(409, { code: "duplicate_content", detail: "dup" });
      return base(url);
    });
    fireEvent.click(await screen.findByRole("button", { name: /Publish/ }));
    expect(await screen.findByText("Add a top or bottom caption first.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Bottom text"), { target: { value: "Same old joke" } });
    fireEvent.click(screen.getByRole("button", { name: /Publish/ }));
    fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Publish" }));
    expect(await screen.findByText(/A very similar meme already exists/)).toBeInTheDocument();
  });

  it("asks guests to log in before creating", async () => {
    renderAt("/meme-zone/create", base, { user: null });
    expect(await screen.findByText(/Log in to make memes/)).toBeInTheDocument();
  });
});
