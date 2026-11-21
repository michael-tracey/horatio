import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { NotificationOut } from "../api/types";
import { NotificationBell, timeAgo } from "./NotificationBell";

describe("timeAgo", () => {
  const now = new Date("2026-10-14T12:00:00Z").getTime();
  const ago = (seconds: number) => new Date(now - seconds * 1000).toISOString();

  it("picks the largest whole unit", () => {
    const format = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    expect(timeAgo(ago(30), now)).toBe(format.format(-30, "second"));
    expect(timeAgo(ago(5 * 60), now)).toBe(format.format(-5, "minute"));
    expect(timeAgo(ago(3 * 3600), now)).toBe(format.format(-3, "hour"));
    expect(timeAgo(ago(26 * 3600), now)).toBe(format.format(-1, "day"));
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const at = new Date().toISOString();
const plain = { troupe_id: "t1", troupe_name: "Lords of the Night", at, read: false, picture: null, player_id: null, player_name: null };
const ITEMS: NotificationOut[] = [
  {
    ...plain,
    id: "teaching:1",
    kind: "teaching",
    task: true,
    summary: "Rook: Teaching Firearms 1 to Konrad (Nick)? It costs 1 Willpower.",
    link: "/play/characters/c1?tab=tracker",
    player_id: "u2",
    player_name: "Nick",
  },
  { ...plain, id: "n1", kind: "downtime.results", task: false, summary: "Your downtime results are in.", link: "/characters/c2" },
];

function Where() {
  const { pathname, search } = useLocation();
  return <p>At {pathname + search}</p>;
}

function show({ beforeSetup = false, at = "/" }: { beforeSetup?: boolean; at?: string } = {}) {
  vi.spyOn(api, "GET").mockImplementation((async (path: string) =>
    path === "/api/notifications"
      ? { data: { items: ITEMS, count: 2 }, response: new Response(null, { status: 200 }) }
      : { error: { detail: "Not found" }, response: new Response(null, { status: 404 }) }) as never);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[at]}>
        <NotificationBell beforeSetup={beforeSetup} />
        <Routes>
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the bell", () => {
  it("links the player a teaching request names to their profile, the line still opening the task (#1131)", async () => {
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Notifications, 2 waiting" }));
    const bell = screen.getByRole("dialog", { name: "Notifications" });
    const task = within(bell).getByRole("button", { name: "Rook: Teaching Firearms 1 to Konrad (Nick)? It costs 1 Willpower." });
    const nick = within(bell).getByRole("link", { name: "Nick" });
    expect(nick.getAttribute("href")).toBe("/players/u2");
    // A message naming nobody is a button as before, with no link in it.
    expect(within(bell).getByRole("button", { name: /Your downtime results are in\./ })).not.toBeNull();
    expect(within(bell).getAllByRole("link").map((l) => l.textContent)).toEqual(["Nick", "Notification settings"]);

    fireEvent.click(task);
    expect(screen.getByText("At /play/characters/c1?tab=tracker")).not.toBeNull();
    expect(screen.queryByRole("dialog", { name: "Notifications" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Notifications, 2 waiting" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Notifications" })).getByRole("link", { name: "Nick" }));
    expect(screen.getByText("At /players/u2")).not.toBeNull();
    expect(screen.queryByRole("dialog", { name: "Notifications" })).toBeNull();
  });

  describe("before two-step sign-in is set up (#1146)", () => {
    const SETUP = "/two-step?next=%2Ftroupes%2Ft1";
    const marked = () =>
      vi.spyOn(api, "POST").mockResolvedValue({ data: null, response: new Response(null, { status: 204 }) } as never);

    it("opens a notice in place, marking it read and showing it in full, without following its link", async () => {
      const post = marked();
      show({ beforeSetup: true, at: SETUP });
      fireEvent.click(await screen.findByRole("button", { name: "Notifications, 2 waiting" }));
      const bell = screen.getByRole("dialog", { name: "Notifications" });
      const message = within(bell).getByRole("button", { name: /Your downtime results are in\./ });
      expect(message.getAttribute("aria-expanded")).toBe("false");
      expect(message.querySelector(".line-clamp-2")).not.toBeNull();

      fireEvent.click(message);

      await waitFor(() => expect(post).toHaveBeenCalledWith("/api/notifications/read", { body: { ids: ["n1"] } }));
      expect(screen.getByText(`At ${SETUP}`)).not.toBeNull();
      expect(screen.getByRole("dialog", { name: "Notifications" })).not.toBeNull();
      expect(message.getAttribute("aria-expanded")).toBe("true");
      expect(message.querySelector(".line-clamp-2")).toBeNull();
      // Its date and time in full, not "now".
      expect(message.querySelector("time")?.textContent).toMatch(/\d{4}/);
    });

    it("opens a task in place too, its player's name plain text, as profiles wait for setup", async () => {
      const post = marked();
      show({ beforeSetup: true, at: SETUP });
      fireEvent.click(await screen.findByRole("button", { name: "Notifications, 2 waiting" }));
      const bell = screen.getByRole("dialog", { name: "Notifications" });
      expect(within(bell).queryByRole("link")).toBeNull();
      const task = within(bell).getByRole("button", { name: /Teaching Firearms 1 to Konrad \(Nick\)/ });

      fireEvent.click(task);

      // A task can't be marked read: it goes when done.
      expect(post).not.toHaveBeenCalled();
      expect(task.getAttribute("aria-expanded")).toBe("true");
      expect(screen.getByText(`At ${SETUP}`)).not.toBeNull();
    });

    it("has a button to the setup form instead of the notification settings, closing the bell", async () => {
      show({ beforeSetup: true, at: SETUP });
      fireEvent.click(await screen.findByRole("button", { name: "Notifications, 2 waiting" }));
      fireEvent.click(within(screen.getByRole("dialog", { name: "Notifications" })).getByRole("button", { name: "Set up two-step sign-in" }));
      expect(screen.queryByRole("dialog", { name: "Notifications" })).toBeNull();
      expect(screen.getByText(`At ${SETUP}`)).not.toBeNull();
    });

    it("goes back to the setup form from a page open before setup, to come back to it after", async () => {
      show({ beforeSetup: true, at: "/help/players" });
      fireEvent.click(await screen.findByRole("button", { name: "Notifications, 2 waiting" }));
      fireEvent.click(within(screen.getByRole("dialog", { name: "Notifications" })).getByRole("button", { name: "Set up two-step sign-in" }));
      expect(screen.getByText("At /two-step?next=%2Fhelp%2Fplayers")).not.toBeNull();
    });
  });
});
