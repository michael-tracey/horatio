import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { api } from "../../api/client";
import type { NotificationSettingsOut, NotificationTopicOut } from "../../api/types";
import { NotificationsPage } from "./NotificationsPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function topic(name: string, title: string, routes: NotificationTopicOut["routes"], more: Partial<NotificationTopicOut> = {}): NotificationTopicOut {
  return { name, title, hint: `About ${title.toLowerCase()}.`, task: false, routes, troupes_send: [], roles: null, ...more };
}

const PAGE: NotificationSettingsOut = {
  email: true,
  groups: [
    {
      name: "account",
      title: "Your account",
      topics: [
        topic("security", "Your account's safety", [{ way: "bell", on: true, always: true }]),
        topic("account_emails", "Sign-in and suspension emails", [{ way: "email", on: true, always: true }]),
      ],
    },
    {
      name: "downtimes",
      title: "Downtimes",
      topics: [
        topic(
          "downtime",
          "Downtime results",
          [
            { way: "bell", on: true, always: false },
            { way: "email", on: false, always: false },
          ],
          { troupes_send: [{ troupe_id: "t1", troupe_name: "Lords of the Night", connectors: ["Discord", "Email"] }] },
        ),
      ],
    },
    {
      name: "boons",
      title: "Boons",
      topics: [topic("boon_reports", "Boons players report", [{ way: "bell", on: true, always: false }], { roles: [] })],
    },
  ],
};

/** The page, with `/api/notification-settings` answering `page`; a choice answers it back. */
function show(page: NotificationSettingsOut = PAGE) {
  vi.spyOn(api, "GET").mockImplementation((async (path: string) => {
    if (path === "/api/notification-settings") return { data: page, response: new Response(null, { status: 200 }) };
    return { error: { detail: "Not found" }, response: new Response(null, { status: 404 }) };
  }) as never);
  const put = vi.spyOn(api, "PUT").mockImplementation((async () => ({ data: page, response: new Response(null, { status: 200 }) })) as never);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <NotificationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return put;
}

describe("Account › Notifications", () => {
  it("lists each kind under its group, with a tick for each way it can come", async () => {
    const put = show();
    const downtimes = await screen.findByRole("region", { name: "Downtimes" });
    expect(within(downtimes).getByText("Downtime results")).toBeTruthy();
    expect(within(downtimes).getByRole("checkbox", { name: "Downtime results: bell" })).toHaveProperty("checked", true);
    const email = within(downtimes).getByRole("checkbox", { name: "Downtime results: email" });
    expect(email).toHaveProperty("checked", false);
    // What the troupe sends itself is said, not chosen.
    expect(within(downtimes).getByText("Lords of the Night also sends them to Discord and by email: the troupe's choice.")).toBeTruthy();

    fireEvent.click(email);
    await vi.waitFor(() => expect(put).toHaveBeenCalledWith("/api/notification-settings", { body: { topic: "downtime", way: "email", on: true } }));
  });

  it("shows the ones that always come as locked, with nothing to tick", async () => {
    show();
    const account = await screen.findByRole("region", { name: "Your account" });
    expect(within(account).getByText("Bell, always")).toBeTruthy();
    expect(within(account).getByText("Email, always")).toBeTruthy();
    expect(within(account).queryAllByRole("checkbox")).toEqual([]);
  });

  it("says where a role's choice will show before the person holds one", async () => {
    show();
    expect(await screen.findByText(/You hold none of these roles now/)).toBeTruthy();
  });

  it("leaves email out where the server can't send it", async () => {
    show({ ...PAGE, email: false });
    expect(await screen.findByText("Email isn't set up on this server, so notifications come only to the bell.")).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: "Downtime results: email" })).toBeNull();
    expect(screen.queryByText("Sign-in and suspension emails")).toBeNull();
    expect(screen.queryByRole("region", { name: "Emails" })).toBeNull();
  });
});
