import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AuthContext } from "../lib/authContext.js";
import { FanProvider } from "../lib/fan.jsx";
import ChooseTeam from "../pages/ChooseTeam.jsx";

const TEAM = { id: "t1", name: "Chitwan Rhinos", short_name: "CHR", city: "Chitwan", primary_color: "#2F5D50", secondary_color: "#F2A541" };
const USER = { id: "u1", email: "fan@example.com", display_name: "Rhino Roar", providers: [], has_password: true };
const json = (status, body) => Promise.resolve(new Response(body === undefined ? null : JSON.stringify(body), { status }));

function mockApi({ joinStatus }) {
  let joined = false;
  return vi.spyOn(globalThis, "fetch").mockImplementation((url, init = {}) => {
    const method = init.method || "GET";
    if (url.endsWith("/teams")) return json(200, { count: 1, results: [TEAM] });
    if (url.endsWith("/fanpage") && method === "POST") {
      joined = joinStatus === 201;
      return json(joinStatus, joined ? { id: "p1" } : { detail: "Server unavailable" });
    }
    if (url.endsWith("/fanpage/me")) {
      return joined ? json(200, { id: "p1", nickname: "Rhino Roar", current_team: TEAM }) : json(403, { detail: "no profile" });
    }
    return json(404, {});
  });
}

function renderPage(user, openAuth = vi.fn()) {
  render(
    <MemoryRouter>
      <AuthContext.Provider value={{ user, status: "ready", openAuth, setUser: vi.fn(), refresh: vi.fn(), logout: vi.fn() }}>
        <FanProvider><ChooseTeam /></FanProvider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
  return openAuth;
}

describe("team selection", () => {
  it("shows confirmation only after the API succeeds, sending the CSRF token", async () => {
    document.cookie = "csrftoken=test-csrf";
    const fetchMock = mockApi({ joinStatus: 201 });
    renderPage(USER);
    expect(screen.getByRole("heading", { name: "Aaja, afno team choose gara!" })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("radio"));
    fireEvent.change(screen.getByLabelText("Nickname"), { target: { value: "Rhino Roar" } });
    fireEvent.click(screen.getByRole("button", { name: /Join the CHR adda/ }));
    expect(await screen.findByRole("heading", { name: /Welcome to the Chitwan Rhinos adda/ })).toBeInTheDocument();
    const join = fetchMock.mock.calls.find(([u, i]) => u.endsWith("/fanpage") && i?.method === "POST");
    expect(join[1].headers["X-CSRFToken"]).toBe("test-csrf");
    expect(join[1].credentials).toBe("include");
    expect(JSON.parse(join[1].body)).toMatchObject({ team: "t1", nickname: "Rhino Roar" });
  });

  it("does not show success when the API call fails", async () => {
    document.cookie = "csrftoken=test-csrf";
    mockApi({ joinStatus: 500 });
    renderPage(USER);
    fireEvent.click(await screen.findByRole("radio"));
    fireEvent.change(screen.getByLabelText("Nickname"), { target: { value: "Rhino Roar" } });
    fireEvent.click(screen.getByRole("button", { name: /Join the CHR adda/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Server unavailable");
    await waitFor(() => expect(screen.queryByText(/Membership confirmed/)).not.toBeInTheDocument());
  });

  it("lets guests browse teams but asks them to log in to join", async () => {
    const fetchMock = mockApi({ joinStatus: 201 });
    const openAuth = renderPage(null);
    fireEvent.click(await screen.findByRole("radio"));
    expect(screen.queryByLabelText("Nickname")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Log in to join CHR/ }));
    expect(openAuth).toHaveBeenCalledWith({ reason: "Log in to join the Chitwan Rhinos adda." });
    expect(fetchMock.mock.calls.some(([u, i]) => u.endsWith("/fanpage") && i?.method === "POST")).toBe(false);
  });
});
