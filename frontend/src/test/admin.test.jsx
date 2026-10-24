import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FeedbackProvider } from "../components/Feedback.jsx";
import { AuthProvider } from "../lib/AuthProvider.jsx";
import AdminApp from "../pages/admin/AdminApp.jsx";

const json = (status, body) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const STAFF = { id: "s1", email: "admin@example.com", display_name: "Admin", avatar_url: "", is_staff: true, providers: [] };
const TEAMS = {
  key: "teams", label: "Teams", group: "Teams & players", note: "", list_display: ["name", "is_active"],
  search: true, filters: ["is_active"], can_create: true, can_update: true, can_delete: true, actions: [],
};
const DASHBOARD = {
  totals: { users: 3, users_new_7d: 1, staff: 1, fans: 2, teams: 1, players: 0, matches_upcoming: 0, matches_live: 0,
    posts_published: 0, posts_pending: 2, reports_open: 0, memes_drafts: 0, memes_7d: 0, polls_open: 0,
    predictions: 0, points_7d: 0 },
  teams: [{ id: "t1", name: "Biratnagar Kings", short_name: "BRK", primary_color: "#112233", members: 2 }],
  pending_posts: [{ id: "p1", title: "Great innings", author: "Bhunte", content_type: "fan_post", created_at: new Date().toISOString() }],
  open_reports: [],
  recent_users: [],
};

function mockApi(user) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((url, init = {}) => {
    if (url.endsWith("/accounts/session")) return json(200, { authenticated: Boolean(user), user });
    if (url.endsWith("/admin/resources")) return json(200, { me: { is_superuser: true, is_moderator: true }, resources: [TEAMS] });
    if (url.endsWith("/admin/dashboard")) return json(200, DASHBOARD);
    if (url.endsWith("/admin/teams") && init.method === "OPTIONS") {
      return json(200, { resource: TEAMS, actions: [], fields: {
        id: { type: "string", read_only: true }, name: { type: "string", label: "Name", read_only: false, required: true },
        is_active: { type: "boolean", label: "Is active", read_only: false },
      } });
    }
    if (url.includes("/admin/teams/bulk")) return json(200, { done: 1, skipped: [] });
    if (url.endsWith("/admin/teams/t1") && init.method === "PATCH") {
      return json(200, { id: "t1", ...JSON.parse(init.body), is_active: true, _label: JSON.parse(init.body).name });
    }
    if (url.endsWith("/admin/teams/t1")) return json(200, { id: "t1", name: "Biratnagar Kings", is_active: true, _label: "Biratnagar Kings" });
    if (url.includes("/admin/teams")) {
      return json(200, { count: 1, next: null, previous: null, results: [{ id: "t1", name: "Biratnagar Kings", is_active: true, _label: "Biratnagar Kings" }] });
    }
    return json(404, {});
  });
}

const renderAt = (path) => render(
  <MemoryRouter initialEntries={[path]}>
    <FeedbackProvider>
      <AuthProvider>
        <Routes><Route path="/staff/*" element={<AdminApp />} /></Routes>
      </AuthProvider>
    </FeedbackProvider>
  </MemoryRouter>,
);

afterEach(() => vi.restoreAllMocks());

describe("admin console", () => {
  it("is closed to non-staff accounts", async () => {
    mockApi({ ...STAFF, is_staff: false });
    renderAt("/staff");
    expect(await screen.findByText("This area is only for staff accounts.")).toBeInTheDocument();
  });

  it("shows the dashboard and navigation for staff", async () => {
    mockApi(STAFF);
    renderAt("/staff");
    expect(await screen.findByText("Great innings")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Teams" })).toHaveAttribute("href", "/staff/teams");
    expect(screen.getByText("Posts to review").closest("a")).toHaveClass("is-alert");
  });

  it("lists a resource from its metadata", async () => {
    mockApi(STAFF);
    renderAt("/staff/teams");
    expect(await screen.findByRole("link", { name: "Biratnagar Kings" })).toHaveAttribute("href", "/staff/teams/t1");
    expect(screen.getByRole("link", { name: /Add/ })).toHaveAttribute("href", "/staff/teams/new");
    expect(screen.getByText("1 total · page 1 of 1")).toBeInTheDocument();
  });

  it("bulk-deletes selected rows after an in-page confirmation", async () => {
    document.cookie = "csrftoken=t";
    const fetchMock = mockApi(STAFF);
    renderAt("/staff/teams");
    fireEvent.click(await screen.findByLabelText("Select all on this page"));
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Delete selected/ }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("Delete 1 record?");
    fireEvent.click(screen.getByRole("button", { name: "Delete 1 record" }));
    expect(await screen.findByText("Deleted 1 record.")).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls.find(([url]) => url.includes("/admin/teams/bulk"));
    expect(JSON.parse(init.body)).toEqual({ action: "delete", ids: ["t1"] });
  });

  it("validates in the page and confirms a save", async () => {
    document.cookie = "csrftoken=t";
    const fetchMock = mockApi(STAFF);
    renderAt("/staff/teams/t1");
    const name = await screen.findByLabelText(/^Name/);
    fireEvent.change(name, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /Save changes/ }));
    expect(await screen.findByText("This field is required.")).toBeInTheDocument();
    expect(screen.getByText("Please fill in the required fields.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
    fireEvent.change(name, { target: { value: "Biratnagar Warriors" } });
    fireEvent.click(screen.getByRole("button", { name: /Save changes/ }));
    expect(await screen.findByText("Saved changes to “Biratnagar Warriors”.")).toBeInTheDocument();
  });
});
