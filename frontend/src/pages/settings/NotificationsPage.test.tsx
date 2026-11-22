import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { api } from "../../api/client";
import type { Me, NotificationSettingsOut, NotificationTopicOut, Preferences } from "../../api/types";
import { DEFAULT_PREFERENCES } from "../../hooks";
import { digestHint, hourName, NotificationsPage } from "./NotificationsPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "serviceWorker");
});

function topic(name: string, title: string, routes: NotificationTopicOut["routes"], more: Partial<NotificationTopicOut> = {}): NotificationTopicOut {
  return { name, title, hint: `About ${title.toLowerCase()}.`, task: false, routes, troupes_send: [], roles: null, ...more };
}

// The server's push key, as base64url: any 65 bytes do here.
const KEY = btoa(String.fromCharCode(...new Uint8Array(65).fill(4)))
  .replaceAll("+", "-")
  .replaceAll("/", "_")
  .replace(/=+$/, "");

const PAGE: NotificationSettingsOut = {
  email: true,
  push: true,
  push_key: KEY,
  devices: [],
  quiet_exempt: ["Powers used in play", "Teaching to confirm"],
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
            { way: "push", on: true, always: false },
          ],
          {
            troupes_send: [
              {
                troupe_id: "t1",
                troupe_name: "Lords of the Night",
                connectors: ["Discord", "Email"],
                own_channels: [{ character_id: "c1", character_name: "Agnes", on: true }],
              },
            ],
          },
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

/** The page, with `/api/notification-settings` answering `page`; a choice answers it back.
 * The person's settings are `prefs`, and a change to them is kept. */
function show(page: NotificationSettingsOut = PAGE, prefs: Partial<Preferences> = {}) {
  let kept: Preferences = { ...DEFAULT_PREFERENCES, ...prefs };
  vi.spyOn(api, "PATCH").mockImplementation((async (_path: string, { body }: { body: Partial<Preferences> }) => {
    kept = { ...kept, ...body };
    return { data: kept, response: new Response(null, { status: 200 }) };
  }) as never);
  vi.spyOn(api, "GET").mockImplementation((async (path: string) => {
    if (path === "/api/notification-settings") return { data: page, response: new Response(null, { status: 200 }) };
    if (path === "/api/auth/me") return { data: { id: "u1", handle: "agnes", display_name: "Agnes", preferences: kept } as Me, response: new Response(null, { status: 200 }) };
    return { error: { detail: "Not found" }, response: new Response(null, { status: 404 }) };
  }) as never);
  const put = vi.spyOn(api, "PUT").mockImplementation((async () => ({ data: page, response: new Response(null, { status: 200 }) })) as never);
  // Turning a device off answers without it.
  let devices = page.devices;
  vi.spyOn(api, "DELETE").mockImplementation((async (_path: string, { params }: { params: { path: { device_id: string } } }) => {
    devices = devices.filter((d) => d.id !== params.path.device_id);
    return { data: { ...page, devices }, response: new Response(null, { status: 200 }) };
  }) as never);
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
  describe("the digest and quiet hours (#1196)", () => {
    it("gathers emails into one a week, on the day and at the hour chosen", async () => {
      show();
      const emails = await screen.findByRole("region", { name: "Emails" });
      expect(within(emails).queryByRole("combobox", { name: "Digest hour" })).toBeNull();
      fireEvent.click(within(emails).getByRole("radio", { name: "Weekly" }));
      await vi.waitFor(() => expect(api.PATCH).toHaveBeenCalledWith("/api/preferences", { body: { email_digest: "weekly" } }));

      const day = await within(emails).findByRole("combobox", { name: "Digest day" });
      fireEvent.change(day, { target: { value: "thursday" } });
      await vi.waitFor(() => expect(api.PATCH).toHaveBeenCalledWith("/api/preferences", { body: { digest_day: "thursday" } }));
      const hour = within(emails).getByRole("combobox", { name: "Digest hour" });
      await vi.waitFor(() => expect(hour).toHaveProperty("disabled", false));
      fireEvent.change(hour, { target: { value: "18" } });
      await vi.waitFor(() => expect(api.PATCH).toHaveBeenCalledWith("/api/preferences", { body: { digest_hour: 18 } }));
      expect(await within(emails).findByText(/One email a week, on Thursday at 6 pm/)).toBeTruthy();
    });

    it("says what still comes at once, and where the time zone comes from", () => {
      const prefs = { ...DEFAULT_PREFERENCES, email_digest: "daily", digest_hour: 7, time_zone: "America/New_York" } as Preferences;
      expect(digestHint(prefs)).toBe(
        "One email a day at 7 am (America/New York), the day's notifications grouped by kind. Word about your account's safety, and announcements marked important, still come at once.",
      );
      expect(digestHint({ ...prefs, email_digest: "at_once" })).toMatch(/^Each email as it happens/);
      expect(digestHint({ ...prefs, time_zone: null })).toContain("(UTC, until you choose a time zone under Preferences)");
      expect([0, 12, 13].map((h) => hourName(h, "12"))).toEqual(["12 am", "12 pm", "1 pm"]);
      expect(hourName(7, "24")).toBe("07:00");
    });

    it("keeps quiet hours for the phone, naming the kinds that still come", async () => {
      show(PAGE, { time_zone: "Europe/London" });
      const quiet = await screen.findByRole("region", { name: "Quiet hours" });
      expect(within(quiet).getByText(/Powers used in play and Teaching to confirm still come at once/)).toBeTruthy();
      expect(within(quiet).queryByLabelText("Quiet hours start")).toBeNull();
      fireEvent.click(within(quiet).getByRole("switch", { name: "Quiet hours" }));
      await vi.waitFor(() => expect(api.PATCH).toHaveBeenCalledWith("/api/preferences", { body: { quiet_hours: true } }));

      const start = await within(quiet).findByLabelText("Quiet hours start");
      expect(start).toHaveProperty("value", "22:00");
      await vi.waitFor(() => expect(start).toHaveProperty("disabled", false));
      fireEvent.change(start, { target: { value: "23:30" } });
      // Saved once left, not at each keystroke.
      expect(api.PATCH).toHaveBeenCalledTimes(1);
      fireEvent.blur(start);
      await vi.waitFor(() => expect(api.PATCH).toHaveBeenCalledWith("/api/preferences", { body: { quiet_start: "23:30" } }));
      expect(within(quiet).getByLabelText("Quiet hours end")).toHaveProperty("value", "08:00");
    });

    it("leaves quiet hours out where the server can't push", async () => {
      show({ ...PAGE, push: false, push_key: null });
      await screen.findByRole("region", { name: "Emails" });
      expect(screen.queryByRole("region", { name: "Quiet hours" })).toBeNull();
    });
  });

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

  it("lets the player turn off their character's own Discord channel", async () => {
    const put = show();
    const downtimes = await screen.findByRole("region", { name: "Downtimes" });
    const own = within(downtimes).getByRole("switch", { name: "Lords of the Night: post to Agnes's own Discord channel" });
    expect(own).toHaveProperty("checked", true);

    fireEvent.click(own);
    await vi.waitFor(() => expect(put).toHaveBeenCalledWith("/api/notification-settings/own-channel", { body: { character_id: "c1", on: false } }));
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
    expect(await screen.findByText("Email isn't set up on this server, so notifications don't come by email.")).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: "Downtime results: email" })).toBeNull();
    expect(screen.queryByText("Sign-in and suspension emails")).toBeNull();
    expect(screen.queryByRole("region", { name: "Emails" })).toBeNull();
  });

  it("leaves the phone out where the server can't push, and says so", async () => {
    show({ ...PAGE, push: false, push_key: null });
    expect(await screen.findByText("Phone notifications aren't set up on this server, so none come to your phone.")).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: "Downtime results: phone" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Phone notifications" })).toBeNull();
  });

  it("chooses which kinds come to the phone", async () => {
    const put = show();
    const phone = await screen.findByRole("checkbox", { name: "Downtime results: phone" });
    expect(phone).toHaveProperty("checked", true);
    fireEvent.click(phone);
    await vi.waitFor(() => expect(put).toHaveBeenCalledWith("/api/notification-settings", { body: { topic: "downtime", way: "push", on: false } }));
  });

  it("turns phone notifications on and off on this device", async () => {
    const browser = pushingBrowser();
    const put = show();
    const here = await screen.findByRole("switch", { name: "On this device" });
    await vi.waitFor(() => expect(here).toHaveProperty("disabled", false));
    expect(here).toHaveProperty("checked", false);

    fireEvent.click(here);
    await vi.waitFor(() =>
      expect(put).toHaveBeenCalledWith("/api/notification-settings/devices", {
        body: { endpoint: "https://fcm.googleapis.com/fcm/send/here", p256dh: "BKey", auth: "secret" },
      }),
    );
    expect(browser.asked).toBe(true);
    // Subscribed with the server's own key.
    expect(Array.from(browser.subscribedWith ?? [])).toEqual(Array(65).fill(4));
  });

  it("turns it off on this device, and on another of yours", async () => {
    const browser = pushingBrowser("https://fcm.googleapis.com/fcm/send/here");
    show({
      ...PAGE,
      devices: [
        { id: "d1", name: "Chrome on Android", endpoint: "https://fcm.googleapis.com/fcm/send/here", created_at: "2026-11-20T12:00:00Z" },
        { id: "d2", name: "iPhone", endpoint: "https://web.push.apple.com/there", created_at: "2026-11-19T12:00:00Z" },
      ],
    });
    const phone = await screen.findByRole("region", { name: "Phone notifications" });
    const here = within(phone).getByRole("switch", { name: "On this device" });
    await vi.waitFor(() => expect(here).toHaveProperty("checked", true));
    // The other device is listed, to turn off from here.
    expect(within(phone).getByText(/iPhone/)).toBeTruthy();
    expect(within(phone).queryByText(/Chrome on Android/)).toBeNull();
    fireEvent.click(within(phone).getByRole("button", { name: "Turn off" }));
    await vi.waitFor(() => expect(api.DELETE).toHaveBeenCalledWith("/api/notification-settings/devices/{device_id}", { params: { path: { device_id: "d2" } } }));

    fireEvent.click(here);
    await vi.waitFor(() => expect(api.DELETE).toHaveBeenCalledWith("/api/notification-settings/devices/{device_id}", { params: { path: { device_id: "d1" } } }));
    await vi.waitFor(() => expect(browser.unsubscribed).toBe(true));
  });

  it("tells someone on an iPhone in Safari to add Horatio to the Home Screen", async () => {
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 Version/18.1 Mobile/15E148 Safari/604.1");
    show();
    expect(await screen.findByText(/add Horatio to your Home Screen first/)).toBeTruthy();
    expect(screen.queryByRole("switch", { name: "On this device" })).toBeNull();
  });
});

/** A browser that can push, through a service worker, with a subscription already at
 * `endpoint` if given. */
function pushingBrowser(endpoint?: string) {
  const browser: { asked: boolean; unsubscribed: boolean; subscribedWith: Uint8Array | null } = { asked: false, unsubscribed: false, subscribedWith: null };
  const subscription = (at: string) => ({
    endpoint: at,
    options: { applicationServerKey: new Uint8Array(65).fill(4).buffer },
    toJSON: () => ({ endpoint: at, keys: { p256dh: "BKey", auth: "secret" } }),
    unsubscribe: async () => {
      browser.unsubscribed = true;
      return true;
    },
  });
  let current = endpoint ? subscription(endpoint) : null;
  const registration = {
    pushManager: {
      getSubscription: async () => current,
      subscribe: async ({ applicationServerKey }: { applicationServerKey: Uint8Array }) => {
        browser.subscribedWith = applicationServerKey;
        current = subscription("https://fcm.googleapis.com/fcm/send/here");
        return current;
      },
    },
  };
  vi.stubGlobal("PushManager", class {});
  vi.stubGlobal("Notification", {
    permission: "default",
    requestPermission: async () => {
      browser.asked = true;
      return "granted";
    },
  });
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { getRegistration: async () => registration, ready: Promise.resolve(registration) } });
  return browser;
}
