import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { FeedbackProvider } from "../components/Feedback.jsx";
import UserMenu from "../components/UserMenu.jsx";
import { api, AUTH_REQUIRED_EVENT } from "../lib/api.js";
import { AuthProvider } from "../lib/AuthProvider.jsx";
import { useAuth } from "../lib/authContext.js";

const json = (status, body) => Promise.resolve(new Response(body === undefined ? null : JSON.stringify(body), { status }));
const USER = { id: "u1", email: "fan@example.com", display_name: "Rhino Roar", avatar_url: "", providers: [], has_password: true };

function Probe() {
  const { user } = useAuth();
  return <p data-testid="who">{user ? user.email : "guest"}</p>;
}

function renderApp() {
  render(
    <MemoryRouter>
      <FeedbackProvider>
        <AuthProvider>
          <UserMenu />
          <Probe />
        </AuthProvider>
      </FeedbackProvider>
    </MemoryRouter>,
  );
}

describe("authentication UI", () => {
  it("logs in with email and shows the avatar menu", async () => {
    document.cookie = "csrftoken=t";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((url, init = {}) => {
      if (url.endsWith("/accounts/session")) return json(200, { authenticated: false, user: null });
      if (url.endsWith("/accounts/login") && init.method === "POST") return json(200, USER);
      if (url.endsWith("/accounts/logout") && init.method === "POST") return json(204);
      return json(404, {});
    });
    renderApp();
    fireEvent.click(await screen.findByRole("button", { name: "Log in" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Google sign-in isn't configured on this site yet.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "fan@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Str0ng-pass-123" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Log in" }).at(-1));
    await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("fan@example.com"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const login = fetchMock.mock.calls.find(([u]) => u.endsWith("/accounts/login"));
    expect(JSON.parse(login[1].body)).toEqual({ email: "fan@example.com", password: "Str0ng-pass-123" });

    fireEvent.click(screen.getByRole("button", { name: "Account menu" }));
    for (const item of ["Profile", "My team", "Settings", "Log out"]) {
      expect(screen.getByRole("menuitem", { name: item })).toBeInTheDocument();
    }
    expect(screen.getByText("Welcome back, Rhino Roar!")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("menuitem", { name: "Log out" }));
    expect(await screen.findByText("Logged out successfully.")).toBeInTheDocument();
    expect(screen.getByTestId("who")).toHaveTextContent("guest");
  });

  it("shows invalid-credential errors and stays logged out", async () => {
    document.cookie = "csrftoken=t";
    vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
      if (url.endsWith("/accounts/session")) return json(200, { authenticated: false, user: null });
      if (url.endsWith("/accounts/login")) return json(401, { code: "invalid_credentials", detail: "Invalid email or password." });
      return json(404, {});
    });
    renderApp();
    fireEvent.click(await screen.findByRole("button", { name: "Log in" }));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "fan@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Log in" }).at(-1));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(screen.getByTestId("who")).toHaveTextContent("guest");
  });

  it("logs out through the menu", async () => {
    document.cookie = "csrftoken=t";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
      if (url.endsWith("/accounts/session")) return json(200, { authenticated: true, user: USER });
      if (url.endsWith("/accounts/logout")) return Promise.resolve(new Response(null, { status: 204 }));
      return json(404, {});
    });
    renderApp();
    fireEvent.click(await screen.findByRole("button", { name: "Account menu" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Log out" }));
    await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("guest"));
    expect(fetchMock.mock.calls.some(([u, i]) => u.endsWith("/accounts/logout") && i.method === "POST")).toBe(true);
  });

  it("opens the login dialog when the API answers 401", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((url) =>
      url.endsWith("/accounts/session") ? json(200, { authenticated: false, user: null }) : json(401, { detail: "Authentication credentials were not provided." }));
    renderApp();
    await screen.findByRole("button", { name: "Log in" });
    await expect(api("/fanpage/me")).rejects.toMatchObject({ status: 401 });
    expect(await screen.findByRole("dialog")).toHaveTextContent("Log in to take part.");
  });

  it("dispatches the auth event only for unexpected 401s", async () => {
    const listener = vi.fn();
    window.addEventListener(AUTH_REQUIRED_EVENT, listener);
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(401, { code: "invalid_credentials" }));
    await expect(api("/accounts/login", { method: "POST", body: {}, silent401: true })).rejects.toBeTruthy();
    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(AUTH_REQUIRED_EVENT, listener);
  });
});
