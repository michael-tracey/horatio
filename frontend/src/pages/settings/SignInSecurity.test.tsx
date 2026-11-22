import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { datesFor } from "../../dates";
import { lastActive, RecentSignInsCard, sessionDetails, SessionsCard } from "./SignInSecurity";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const dates = datesFor({ time_zone: "UTC", date_format: "day_month", clock: "24h" } as never);
const NOW = Date.parse("2026-11-22T12:00:00Z");

const here = {
  id: "here",
  device: "Firefox on Windows",
  signed_in_at: "2026-11-20T09:00:00Z",
  last_active_at: "2026-11-22T11:58:00Z",
  place: "203.0.113.…",
  this_device: true,
};
const phone = { ...here, id: "phone", device: "Safari on iPhone", last_active_at: "2026-11-21T18:30:00Z", place: null, this_device: false };

function answering(get: Record<string, unknown>) {
  vi.spyOn(api, "GET").mockImplementation((async (path: string) => ({ data: get[path] ?? null, response: new Response(null, { status: 200 }) })) as never);
  return vi.spyOn(api, "POST").mockImplementation((async () => ({ data: { ended: 1 }, response: new Response(null, { status: 200 }) })) as never);
}

function show(card: React.ReactNode) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{card}</QueryClientProvider>);
}

describe("when a sign-in was last used (#1193)", () => {
  it("is 'in the last few minutes' while the server may not have noted it yet", () => {
    expect(lastActive("2026-11-22T11:57:00Z", dates, NOW)).toBe("Active in the last few minutes");
    expect(lastActive("2026-11-22T11:50:00Z", dates, NOW)).toBe(`Last active ${dates.dateTime("2026-11-22T11:50:00Z")}`);
    expect(lastActive(null, dates, NOW)).toBeNull();
  });

  it("goes after when it started, with where only when it's known", () => {
    expect(sessionDetails(here, dates, NOW)).toBe(`Signed in ${dates.dateTime(here.signed_in_at)}, active in the last few minutes, from 203.0.113.…`);
    expect(sessionDetails({ ...phone, last_active_at: null }, dates, NOW)).toBe(`Signed in ${dates.dateTime(phone.signed_in_at)}`);
  });
});

describe("where you're signed in (#1193)", () => {
  it("marks this device, and signs out another on its own", async () => {
    const post = answering({ "/api/account/sessions": [here, phone] });
    show(<SessionsCard />);
    const rows = (await screen.findAllByRole("listitem")) as [HTMLElement, HTMLElement];
    expect(within(rows[0]).getByText("This device")).toBeTruthy();
    expect(within(rows[0]).queryByRole("button", { name: /Sign out/ })).toBeNull();
    fireEvent.click(within(rows[1]).getByRole("button", { name: /Sign out on Safari on iPhone/ }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/account/sessions/{session_id}/sign-out", { params: { path: { session_id: "phone" } } }));
  });

  it("signs out everywhere else at once, asking no password", async () => {
    const post = answering({ "/api/account/sessions": [here, phone] });
    show(<SessionsCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Sign out everywhere else" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/account/sessions/sign-out-others"));
    expect(screen.queryByLabelText(/password/i)).toBeNull();
  });

  it("says so when this is the only one", async () => {
    answering({ "/api/account/sessions": [here] });
    show(<SessionsCard />);
    expect(await screen.findByText("You're signed in only here.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Sign out everywhere else" })).toBeNull();
  });
});

describe("recent sign-ins (#1193)", () => {
  const signIns = [
    { at: "2026-11-22T11:00:00Z", outcome: "signed_in", how: "Password, then authenticator app", place: "203.0.113.…" },
    { at: "2026-11-22T10:59:00Z", outcome: "failed", how: "A wrong code from the authenticator app", place: null },
  ];

  it("lists each with how and where, and what failed", async () => {
    answering({ "/api/account/sign-ins": { sign_ins: signIns } });
    show(<RecentSignInsCard />);
    const [first, second] = (await screen.findAllByRole("listitem")) as [HTMLElement, HTMLElement];
    expect(first.textContent).toContain("Password, then authenticator app");
    expect(first.textContent).toMatch(/2026, .+, from 203\.0\.113\.…/);
    expect(within(first).getByText("Signed in")).toBeTruthy();
    expect(within(second).getByText("Failed")).toBeTruthy();
    // Where only when the custodian shows IP addresses: the server sends none otherwise (#1205).
    expect(second.textContent).not.toContain(", from");
  });

  it("says nothing of what the log keeps, as it keeps every sign-in (#1205)", async () => {
    answering({ "/api/account/sign-ins": { sign_ins: [] } });
    show(<RecentSignInsCard />);
    expect(await screen.findByText("None that Horatio's log keeps.")).toBeTruthy();
    expect(screen.queryByText(/only while the custodian/)).toBeNull();
  });
});
