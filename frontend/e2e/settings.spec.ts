import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, PASSWORD, shots, person, characterTab, makeCustodian, builtVampire, ATTRIBUTES_AND_FOCUSES, topBar } from "./support";

/** A person's account and settings: handle, password, dates, text size, notifications and the Play View. */

closeContextsAfterEach();

test("settings are kept on the account, and each change says it is saved", async ({ browser }) => {
  const { page } = await person(browser, "settings-player");
  await (await topBar(page)).getByRole("link", { name: "settings-player" }).click();
  await page.locator("main").getByRole("link", { name: "Preferences", exact: true }).click();
  await expect(page).toHaveURL(/\/account\/preferences$/);
  await page.getByRole("radiogroup", { name: "Show ratings as" }).getByRole("radio", { name: "Pips" }).click();
  await expect(page.getByRole("radiogroup", { name: "Show ratings as" }).getByRole("radio", { name: "Pips" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText("Show ratings as: Pips. Saved.")).toBeVisible();
  // While a change is saving, the other settings wait for it, so none is lost.
  await page.route("**/api/preferences", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    await route.continue();
  });
  await page.getByRole("radiogroup", { name: "Paper" }).getByRole("radio", { name: "A4" }).click();
  const clock24 = page.getByRole("radiogroup", { name: "Clock" }).getByRole("radio", { name: "21:30" });
  await expect(clock24).toBeDisabled();
  await expect(page.getByText("Saving…")).toBeVisible();
  await expect(clock24).toBeEnabled();
  await page.unroute("**/api/preferences");
  const saved = page.waitForResponse("**/api/preferences");
  await clock24.click();
  await saved;
  // Saved on the account: all three are still set after a reload.
  await page.reload();
  await expect(page.getByRole("radiogroup", { name: "Show ratings as" }).getByRole("radio", { name: "Pips" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("radiogroup", { name: "Paper" }).getByRole("radio", { name: "A4" })).toHaveAttribute("aria-checked", "true");
  await expect(clock24).toHaveAttribute("aria-checked", "true");
  // The time zone box fits its words, and the hint names this device's zone.
  await expect(page.getByLabel("Time zone")).toHaveAttribute("placeholder", "Follow this device");
  await expect(page.getByText(/This device is on .+ time\./)).toBeVisible();
  await page.screenshot(shots("settings"));
});

test("account settings are in two tabs, Preferences and Sign-in and email, each one column (#910)", async ({ browser }) => {
  const { page } = await person(browser, "account-tabs", { viewport: { width: 375, height: 800 } });
  const cards = () => page.locator("main section > header h2").allTextContents();
  const tall = () => page.evaluate(() => document.documentElement.scrollHeight);
  // The old address lands on Preferences, and its #notifications on the notifications.
  await page.goto("/account/settings");
  await expect(page).toHaveURL(/\/account\/preferences$/);
  await expect(page.getByRole("radiogroup", { name: "Theme" })).toBeVisible();
  expect(await cards()).toEqual(["Appearance", "Sheets", "Dates and times", "At game", "Troupes"]);
  // On a phone, a choice sits under its label, unless it is short enough to sit beside it.
  const under = async (name: string) => {
    const label = await page.getByText(name, { exact: true }).boundingBox();
    const choice = await page.getByRole("radiogroup", { name }).boundingBox();
    return choice!.y >= label!.y + label!.height;
  };
  expect(await under("Badge size")).toBe(true);
  expect(await under("Paper")).toBe(false);
  await page.screenshot(shots("account-preferences-phone"));

  // The old addresses of the notification settings land on Account › Notifications (#1053).
  for (const old of ["/account/settings#notifications", "/account/sign-in#notifications"]) {
    await page.goto(old);
    await expect(page).toHaveURL(/\/account\/notifications$/);
    await expect(page.getByRole("region", { name: "Your account" })).toBeVisible();
  }
  await page.goto("/account/sign-in");
  await expect(page.getByLabel("Your handle")).toBeVisible();
  expect(await cards()).toEqual(["Email", "Handle", "Password"]);
  // Under 2000 px on a phone, on a server that can't send email, as this suite's can't.
  expect(await tall()).toBeLessThan(2000);
  await page.screenshot(shots("account-sign-in-phone"));

  // The profile is what others see, and nothing about signing in.
  await page.locator("main").getByRole("link", { name: "Profile", exact: true }).click();
  await expect(page.getByLabel("Bio")).toBeVisible();
  await expect(page.getByLabel("Your handle")).toHaveCount(0);

  // On a desktop, a choice sits beside its label, in one column no wider than max-w-2xl.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/account/preferences");
  const wide = await page.getByText("Badge size", { exact: true }).boundingBox();
  const beside = await page.getByRole("radiogroup", { name: "Badge size" }).boundingBox();
  expect(beside!.x).toBeGreaterThan(wide!.x + wide!.width);
  const sheets = await page.locator("section", { has: page.getByRole("heading", { name: "Sheets", exact: true }) }).boundingBox();
  expect(sheets!.width).toBeLessThanOrEqual(672);
  await page.screenshot(shots("account-preferences-desktop"));
});

test("Show ratings as is kept through signing out and in, a reload and another device, and the NPC builder follows it", async ({ browser }) => {
  test.slow();
  const custodian = await person(browser, "ratingset-cust");
  makeCustodian(custodian.email);
  // The storyteller's own phone, which keeps what it last had for them (#502).
  const lead = await person(browser, "ratingset-lead", { storageState: { cookies: [], origins: [] } });
  const p = lead.page;
  await p.getByRole("dialog", { name: "Your own phone?" }).getByRole("button", { name: "Yes, keep them here" }).click();
  const headers = { "X-Horatio": "1" };
  const troupe = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Kept Ratings ${run}`, lead_handle: lead.handle } });
  expect(troupe.status(), await troupe.text()).toBe(201);
  const made = await p.request.post(`/api/troupes/${(await troupe.json()).id}/npcs`, { headers, data: { name: "Vespertine", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category: "attributes", name: "Physical", rating: 7, detail: "" } });
  expect(rated.status(), await rated.text()).toBe(200);

  const choose = async (page: Page, ratings: "Numbers" | "Pips") => {
    await page.goto("/account/preferences");
    const radio = page.getByRole("radiogroup", { name: "Show ratings as" }).getByRole("radio", { name: ratings });
    await expect(radio).toBeVisible();
    if ((await radio.getAttribute("aria-checked")) === "true") return;
    await Promise.all([page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.ok()), radio.click()]);
  };
  // The NPC builder's buttons and the Play View's sheet show ratings as the setting says.
  const shows = async (page: Page, ratings: "Numbers" | "Pips") => {
    await page.goto(`/characters/${npc}`);
    await expect(page.getByRole("button", { name: "Physical 7" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "Physical 7" })).toHaveText(ratings === "Numbers" ? "7" : "●");
    await expect(page.getByRole("button", { name: "Physical 8" })).toHaveText(ratings === "Numbers" ? "8" : "○");
    await page.goto(`/play/characters/${npc}`);
    await page.getByRole("tab", { name: "Sheet" }).click();
    await expect(page.getByLabel("7 dots").first()).toBeVisible();
    await expect(page.getByRole("img", { name: "7 dots" })).toHaveCount(ratings === "Pips" ? 1 : 0);
  };

  await choose(p, "Pips");
  await shows(p, "Pips");
  await choose(p, "Numbers");
  await shows(p, "Numbers");
  await p.goto(`/characters/${npc}`);
  await expect(p.getByRole("button", { name: "Physical 7" })).toBeVisible();
  await p.screenshot(shots("npc-builder-numbers"));

  // Signed out and in again: numbers straight away, and after a reload.
  await p.goto("/characters");
  await (await topBar(p)).getByRole("button", { name: "Sign out" }).click();
  await p.getByLabel("Email or handle").fill(lead.email);
  await p.getByLabel("Password").fill(PASSWORD);
  await p.getByRole("button", { name: "Sign in" }).click();
  await expect(p.getByRole("heading", { name: "Your characters" })).toBeVisible();
  await shows(p, "Numbers");
  await p.reload();
  await shows(p, "Numbers");

  // Changed on another device: this one shows it as it opens again, however
  // recently it kept its own copy.
  const other = await (await browser.newContext()).newPage();
  await other.goto("/sign-in");
  await other.getByLabel("Email or handle").fill(lead.email);
  await other.getByLabel("Password").fill(PASSWORD);
  await other.getByRole("button", { name: "Sign in" }).click();
  await expect(other.getByRole("heading", { name: "Your characters" })).toBeVisible();
  await choose(other, "Pips");
  await p.reload();
  await shows(p, "Pips");
  await p.goto(`/characters/${npc}`);
  await expect(p.getByRole("button", { name: "Physical 7" })).toBeVisible();
  await p.screenshot(shots("npc-builder-pips"));
});

test("Account › Notifications: where each kind comes, the ones that always come, and email once the server can send it (#1053)", async ({ browser }) => {
  const { page } = await person(browser, "email-player");
  await (await topBar(page)).getByRole("link", { name: "email-player" }).click();
  await page.locator("main").getByRole("link", { name: "Notifications", exact: true }).click();
  await expect(page).toHaveURL(/\/account\/notifications$/);
  // This suite's server has no email set up, and the page says so: only the bell.
  await expect(page.getByText("Email isn't set up on this server, so notifications don't come by email.")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Downtime results: email" })).toHaveCount(0);
  // Every group a player gets; staff work only for staff.
  const groups = page.locator("main section > header h2");
  await expect(groups).toHaveText(["Your account", "Your characters", "Downtimes", "Boons", "Troupe news"]);
  // Word about your account always comes, with nothing to turn off.
  const account = page.getByRole("region", { name: "Your account" });
  await expect(account.getByText("Bell, always").first()).toBeVisible();
  await expect(account.getByRole("checkbox")).toHaveCount(0);

  // A kind turned off in the bell is kept on the account.
  const renames = page.getByRole("checkbox", { name: "Character renames: bell" });
  await expect(renames).toBeChecked();
  await renames.uncheck();
  await expect(page.getByText("Character renames, bell: off. Saved.")).toBeVisible();
  await page.reload();
  await expect(renames).not.toBeChecked();

  // Where email is set up, each kind but announcements is off by email until ticked.
  await page.route("**/api/notification-settings", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), email: true } });
  });
  await page.reload();
  await expect(page.getByRole("checkbox", { name: "Troupe announcements: email" })).toBeChecked();
  const downtime = page.getByRole("checkbox", { name: "Downtime results: email" });
  await expect(downtime).not.toBeChecked();
  await downtime.check();
  await expect(page.getByText("Downtime results, email: on. Saved.")).toBeVisible();
  await expect(page.getByText("Email, always")).toBeVisible();
  await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.ok()),
    page.getByRole("radiogroup", { name: "Send emails" }).getByRole("radio", { name: "Once a day" }).click(),
  ]);
  await expect(page.getByText(/gathers them into one email at 8 am/)).toBeVisible();
  await page.reload();
  await expect(downtime).toBeChecked();
  await expect(page.getByRole("radiogroup", { name: "Send emails" }).getByRole("radio", { name: "Once a day" })).toHaveAttribute("aria-checked", "true");
  await page.screenshot(shots("settings-notifications"), { fullPage: true });
  await page.setViewportSize({ width: 375, height: 800 });
  await page.screenshot(shots("settings-notifications-phone"), { fullPage: true });

  // An unsubscribe link that isn't real says so, and where to choose instead.
  await page.goto("/unsubscribe/not-a-real-link");
  await expect(page.getByText(/This unsubscribe link doesn't work/)).toBeVisible();
  await expect(page.getByText(/Account › Notifications/)).toBeVisible();
});

/**
 * Phone notifications (#1054). This suite's server has no push key and no push service
 * can reach a test browser, so: the page says push isn't set up; then it is shown as set
 * up, the browser's push manager answers with a made-up subscription, and the devices are
 * kept by the test, while the kinds chosen for the phone are saved for real. The service
 * worker is the app's own, with the push handlers imported. Headless Chrome shows no
 * notifications, so a push handed to it can't be seen here. Sending real pushes is
 * covered by tests/test_web_push.py.
 */
test("phone notifications: turned on on this device, which kinds come, and turned off (#1054)", async ({ browser }) => {
  const { page } = await person(browser, "phone-pusher", { serviceWorkers: "allow", permissions: ["notifications"] });
  await page.goto("/account/notifications");
  await expect(page.getByText("Phone notifications aren't set up on this server, so none come to your phone.")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Downtime results: phone" })).toHaveCount(0);

  const endpoint = "https://fcm.googleapis.com/fcm/send/e2e-phone-pusher";
  await page.addInitScript((at) => {
    const subscription = {
      endpoint: at,
      options: { applicationServerKey: null },
      toJSON: () => ({ endpoint: at, keys: { p256dh: "BPhone", auth: "secret" } }),
      unsubscribe: async () => (localStorage.removeItem("e2e.push"), true),
    };
    PushManager.prototype.getSubscription = async () => (localStorage.getItem("e2e.push") ? (subscription as unknown as PushSubscription) : null);
    PushManager.prototype.subscribe = async () => (localStorage.setItem("e2e.push", "1"), subscription as unknown as PushSubscription);
  }, endpoint);
  let devices: { id: string; name: string; endpoint: string; created_at: string }[] = [];
  const turnedOn: unknown[] = [];
  const key = "B" + "A".repeat(86);
  await page.route("**/api/notification-settings", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), push: true, push_key: key, devices } });
  });
  await page.route("**/api/notification-settings/devices**", async (route) => {
    const request = route.request();
    if (request.method() === "PUT") {
      turnedOn.push(request.postDataJSON());
      devices = [{ id: "d1", name: "Chrome on Android", endpoint, created_at: new Date().toISOString() }];
    } else devices = [];
    const response = await route.fetch({ url: route.request().url().replace(/\/devices.*$/, ""), method: "GET" });
    await route.fulfill({ response, json: { ...(await response.json()), push: true, push_key: key, devices } });
  });
  await page.reload();

  const phone = page.getByRole("region", { name: "Phone notifications" });
  const here = phone.getByRole("switch", { name: "On this device" });
  await expect(here).not.toBeChecked();
  await expect(here).toBeEnabled();
  // Pushed until turned off: downtime results, boons and the like; not the rest until ticked.
  await expect(page.getByRole("checkbox", { name: "Downtime results: phone" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Your boons: phone" })).toBeChecked();
  const renames = page.getByRole("checkbox", { name: "Character renames: phone" });
  await expect(renames).not.toBeChecked();

  await here.click();
  await expect(page.getByText("Phone notifications are on for this device.")).toBeVisible();
  await expect(here).toBeChecked();
  expect(turnedOn).toEqual([{ endpoint, p256dh: "BPhone", auth: "secret" }]);
  await renames.check();
  await expect(page.getByText("Character renames, phone: on. Saved.")).toBeVisible();
  await page.reload();
  await expect(here).toBeChecked();
  await expect(renames).toBeChecked();

  // The app's one service worker, the one keeping it offline, shows the pushes too.
  const worker = await page.evaluate(async () => (await navigator.serviceWorker.ready).active?.scriptURL ?? "");
  expect(await (await page.request.get(worker)).text()).toContain('importScripts("push-sw.js")');
  const shows = await (await page.request.get("/push-sw.js")).text();
  for (const handled of ['"push"', '"notificationclick"', '"pushsubscriptionchange"']) expect(shows).toContain(`self.addEventListener(${handled}`);

  // Turned off here: the device goes, and the browser's subscription with it.
  await here.click();
  await expect(page.getByText("Phone notifications are off for this device.")).toBeVisible();
  await expect(here).not.toBeChecked();
  expect(devices).toEqual([]);
  expect(await page.evaluate(() => localStorage.getItem("e2e.push"))).toBeNull();
});

test("a handle to be found by, and to sign in with", async ({ browser }) => {
  const { page } = await person(browser, "handle-player");
  // On Sign-in and email, with the email it signs in beside.
  await (await topBar(page)).getByRole("link", { name: "handle-player" }).click();
  await page.locator("main").getByRole("link", { name: "Sign-in and email", exact: true }).click();
  await expect(page.getByLabel("Your handle")).toHaveValue(`handle-player_${run.slice(-10)}`);
  const handle = `Owl_${run.slice(-10)}`;
  await page.getByLabel("Your handle").fill(handle);
  await page.getByRole("button", { name: "Save handle" }).click();
  await expect(page.getByText(`Your handle is now @${handle}.`)).toBeVisible();
  await expect(page.getByText(/^You can change it again on /)).toBeVisible();
  await page.screenshot(shots("settings-handle"));

  // Signing in with it, in any case, from another browser.
  const other = await (await browser.newContext()).newPage();
  await other.goto("/sign-in");
  await other.getByLabel("Email or handle").fill(handle.toLowerCase());
  await other.getByLabel("Password").fill(PASSWORD);
  await other.getByRole("button", { name: "Sign in" }).click();
  await expect(other.getByRole("heading", { name: "Your characters" })).toBeVisible();
});

test("the profile asks before going to another page with changes not saved: Cancel keeps them, Leave drops them (#622)", async ({ browser }) => {
  const { page } = await person(browser, "unsaved-profile");
  await (await topBar(page)).getByRole("link", { name: "unsaved-profile" }).click();
  const bio = page.getByLabel("Bio");
  await bio.fill("Half a thought about a Brujah.");
  const troupes = async () => (await topBar(page)).getByRole("link", { name: "Troupes", exact: true });
  const leaving = page.getByRole("dialog", { name: "Leave this page?" });

  // Cancel stays on the profile, with the change still there to save.
  await (await troupes()).click();
  await expect(leaving).toBeVisible();
  await expect(leaving.getByText("Your changes here aren't saved. Leave anyway? They'll be lost.")).toBeVisible();
  await page.screenshot(shots("leave-unsaved"));
  await leaving.getByRole("button", { name: "Cancel" }).click();
  await expect(leaving).toBeHidden();
  await expect(page).toHaveURL(/\/account$/);
  await expect(bio).toHaveValue("Half a thought about a Brujah.");
  await expect(page.getByText("Not saved yet")).toBeVisible();

  // Leave goes on, and the change is gone.
  await (await troupes()).click();
  await leaving.getByRole("button", { name: "Leave" }).click();
  await expect(page).toHaveURL(/\/troupes$/);
  await (await topBar(page)).getByRole("link", { name: "unsaved-profile" }).click();
  await expect(bio).toHaveValue("");
});

test("a signed-in person changes their password, and signs in with the new one", async ({ browser }) => {
  const { page, email } = await person(browser, "pwchange-player");
  // Signed in on another device too, which the change signs out.
  const other = await (await browser.newContext()).newPage();
  await other.goto("/sign-in");
  await other.getByLabel("Email or handle").fill(email);
  await other.getByLabel("Password").fill(PASSWORD);
  await other.getByRole("button", { name: "Sign in" }).click();
  await expect(other.getByRole("heading", { name: "Your characters" })).toBeVisible();

  await (await topBar(page)).getByRole("link", { name: "Your account" }).click();
  await page.locator("main").getByRole("link", { name: "Sign-in and email", exact: true }).click();
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Password", exact: true }) });
  const newPassword = "a much longer passphrase";
  // The wrong current password is refused.
  await card.getByLabel("Current password").fill("not my password");
  await card.getByLabel("New password").fill(newPassword);
  await card.getByRole("button", { name: "Save new password" }).click();
  await expect(card.getByText("That's not your current password.")).toBeVisible();
  await card.getByLabel("Current password").fill(PASSWORD);
  await card.getByRole("button", { name: "Save new password" }).click();
  await expect(page.getByText("Password changed. You're signed out everywhere else.")).toBeVisible();
  await expect(card.getByLabel("New password")).toHaveValue("");
  await page.screenshot(shots("settings-password"));

  // Still signed in here; the other device is signed out.
  await page.reload();
  await expect(card.getByLabel("Current password")).toBeVisible();
  await other.reload();
  await expect(other.getByRole("button", { name: "Sign in" })).toBeVisible();

  // The old password no longer signs in; the new one does.
  await other.getByLabel("Email or handle").fill(email);
  await other.getByLabel("Password").fill(PASSWORD);
  await other.getByRole("button", { name: "Sign in" }).click();
  await expect(other.getByText("Wrong email, handle or password.")).toBeVisible();
  await other.getByLabel("Password").fill(newPassword);
  await other.getByRole("button", { name: "Sign in" }).click();
  await expect(other.getByRole("heading", { name: "Your characters" })).toBeVisible();
});

test("the bell links to the notification settings", async ({ browser }) => {
  const { page } = await person(browser, "bellsettings-pl");
  await page.getByRole("button", { name: /^Notifications/ }).click();
  await page.getByRole("dialog", { name: "Notifications" }).getByRole("link", { name: "Notification settings" }).click();
  await expect(page).toHaveURL(/\/account\/notifications$/);
  await expect(page.getByRole("region", { name: "Your account" })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Notifications" })).toHaveCount(0);
});

test("dates and times show in each person's zone and format", async ({ browser }) => {
  const { page } = await person(browser, "dates-player");
  // A rename puts a line in the character's log, on the default 12-hour clock in this device's zone.
  await page.goto("/characters");
  await page.getByLabel("Name").fill("Odile Marchand");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  await page.getByRole("button", { name: "More for Odile Marchand" }).click();
  await page.getByRole("menuitem", { name: "Rename…" }).click();
  await page.getByLabel("New name").fill("Odile Brun");
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Odile Brun");
  await characterTab(page, "Log");
  const renamed = page.locator("main time").first();
  await expect(renamed).toHaveText(/^\d{1,2} [A-Z][a-z]{2} \d{4}, \d{1,2}:\d{2} [ap]m$/);
  const log = page.url();

  // In Tokyo, as ISO dates on a 24-hour clock: the page says at once how a deadline will show.
  // Each change is waited for, to be sure it is saved before the next page.
  const saved = () => page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.request().method() === "PATCH" && r.ok());
  await page.goto("/account/preferences");
  await Promise.all([saved(), page.getByLabel("Time zone").fill("Asia/Tokyo")]);
  await Promise.all([saved(), page.getByRole("radiogroup", { name: "Dates" }).getByRole("radio", { name: "2026-10-20" }).click()]);
  await Promise.all([saved(), page.getByRole("radiogroup", { name: "Clock" }).getByRole("radio", { name: "21:30" }).click()]);
  await expect(page.getByText(/^[A-Z][a-z]{2} \d{4}-\d{2}-\d{2}, \d{2}:\d{2} GMT\+9$/)).toBeVisible();
  await page.screenshot(shots("settings-dates"));
  await page.goto(log);
  const at = new Date((await renamed.getAttribute("datetime")) ?? "");
  const part = (type: string, parts: Intl.DateTimeFormatPart[]) => parts.find((p) => p.type === type)?.value;
  const tokyo = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(at);
  await expect(renamed).toHaveText(`${part("year", tokyo)}-${part("month", tokyo)}-${part("day", tokyo)}, ${part("hour", tokyo)}:${part("minute", tokyo)}`);
  await page.screenshot(shots("log-dates"));

  // Back to this device's zone: the zone is cleared, and kept that way after a reload.
  await page.goto("/account/preferences");
  await Promise.all([saved(), page.getByRole("button", { name: "Use this device's" }).click()]);
  await expect(page.getByLabel("Time zone")).toHaveValue("");
  await page.reload();
  await expect(page.getByLabel("Time zone")).toHaveValue("");
  await expect(page.getByText(/^[A-Z][a-z]{2} \d{4}-\d{2}-\d{2}, \d{2}:\d{2} \S+$/)).toBeVisible();
});

test("large text makes the app bigger, but not printed sheets and badges", async ({ browser }) => {
  const { page } = await person(browser, "large-text");
  await page.getByLabel("Name").fill("Squint");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  const character = new URL(page.url()).pathname.split("/")[2]!;
  const fontSize = () => page.evaluate(() => getComputedStyle(document.documentElement).fontSize);
  const normal = await fontSize();

  await (await topBar(page)).getByRole("link", { name: "large-text" }).click();
  await page.locator("main").getByRole("link", { name: "Preferences", exact: true }).click();
  const saved = page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.ok());
  await page.getByRole("radiogroup", { name: "Text size" }).getByRole("radio", { name: "Large" }).click();
  // At once, with no reload, and still after one (once it has saved).
  await expect.poll(fontSize).not.toBe(normal);
  const large = await fontSize();
  expect(parseFloat(large) / parseFloat(normal)).toBeCloseTo(1.15);
  await saved;
  await page.reload();
  await expect(page.getByRole("radiogroup", { name: "Text size" }).getByRole("radio", { name: "Large" })).toHaveAttribute("aria-checked", "true");
  await expect.poll(fontSize).toBe(large);
  await page.screenshot(shots("settings-large-text"));

  // The Play View too.
  await page.goto(`/play/characters/${character}`);
  await expect(page.getByText("Squint").first()).toBeVisible();
  await expect.poll(fontSize).toBe(large);
  // But the printed sheet and badge keep their own sizes.
  await page.goto(`/print/characters/${character}`);
  await expect(page.getByText("Squint").first()).toBeVisible();
  expect(await fontSize()).toBe(normal);
  await page.goto(`/print/characters/${character}/badge`);
  await expect(page.getByText("Squint").first()).toBeVisible();
  expect(await fontSize()).toBe(normal);

  // And back to normal.
  await page.goto("/account/preferences");
  await expect.poll(fontSize).toBe(large);
  await page.getByRole("radiogroup", { name: "Text size" }).getByRole("radio", { name: "Normal" }).click();
  await expect.poll(fontSize).toBe(normal);
});

test("light mode lets the sun rise, and the person at the screen goes to ash, signed out", async ({ browser }) => {
  test.slow();
  const { page } = await person(browser, "sun-at-dawn");
  await page.goto("/account/preferences");
  const theme = page.getByRole("radiogroup", { name: "Theme" });
  await expect(theme.getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
  await theme.getByRole("radio", { name: "Light" }).click();
  await expect(page.getByRole("status").filter({ hasText: "The sun rises" })).toBeAttached();
  const shot = (name: string) => ({ path: shots(name).path });
  await page.waitForTimeout(2500);
  await page.screenshot(shot("sunrise-night"));
  await page.waitForTimeout(2500);
  await page.screenshot(shot("sunrise-dawn"));
  // Signed out as the screen goes white, and the ash blows away to the sign-in page.
  await expect(page).toHaveURL(/\/sign-in/, { timeout: 15_000 });
  await page.waitForTimeout(3600);
  await page.screenshot(shot("sunrise-ash"));
  await expect(page.getByRole("status").filter({ hasText: "The sun rises" })).not.toBeAttached({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  // Truly signed out: the account is behind sign-in again.
  await page.goto("/account/preferences");
  await expect(page).toHaveURL(/\/sign-in/);
});

test("Ultra goth: velvet curtains close, it is saved behind them, and they open on deep red; Dark switches straight back", async ({ browser }) => {
  const { page } = await person(browser, "goth-curtains");
  // What the page shows as it is read, before the app starts: no flash of Dark on a reload.
  await page.context().addInitScript(() => {
    document.addEventListener("readystatechange", () => {
      if (document.readyState === "interactive") (window as unknown as { themeAtLoad: string | null }).themeAtLoad = document.documentElement.getAttribute("data-theme");
    });
  });
  await page.goto("/account/preferences");
  const theme = page.getByRole("radiogroup", { name: "Theme" });
  const html = page.locator("html");
  const bar = page.locator('meta[name="theme-color"]');
  await expect(theme.getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
  await expect(html).not.toHaveAttribute("data-theme");
  const night = () => page.evaluate(() => getComputedStyle(document.documentElement).backgroundColor);
  expect(await night()).toBe("rgb(20, 16, 22)");

  const saved = () => page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.ok());
  const goth = saved();
  await theme.getByRole("radio", { name: "Ultra goth" }).click();
  const curtains = page.getByTestId("curtains");
  await expect(curtains).toHaveAttribute("data-phase", "closing");
  await expect(curtains).toHaveAttribute("data-phase", "opening", { timeout: 10_000 });
  await expect(html).toHaveAttribute("data-theme", "ultragoth");
  await expect(curtains).toHaveCount(0, { timeout: 10_000 });
  await goth;
  await expect(theme.getByRole("radio", { name: "Ultra goth" })).toHaveAttribute("aria-checked", "true");
  await expect(bar).toHaveAttribute("content", "#0a0909");
  expect(await night()).toBe("rgb(10, 9, 9)");

  // Kept on the account, and on the device: set before the app starts.
  await page.reload();
  await expect(theme.getByRole("radio", { name: "Ultra goth" })).toHaveAttribute("aria-checked", "true");
  expect(await page.evaluate(() => (window as unknown as { themeAtLoad: string | null }).themeAtLoad)).toBe("ultragoth");
  await expect(html).toHaveAttribute("data-theme", "ultragoth");
  await page.screenshot(shots("ultragoth-settings"));

  // Back to Dark at once, with no curtains.
  const dark = saved();
  await theme.getByRole("radio", { name: "Dark" }).click();
  await expect(html).not.toHaveAttribute("data-theme");
  await expect(curtains).toHaveCount(0);
  await expect(bar).toHaveAttribute("content", "#141016");
  await dark;
  await page.reload();
  await expect(theme.getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
  expect(await page.evaluate(() => (window as unknown as { themeAtLoad: string | null }).themeAtLoad)).toBeNull();
});

test("Ultra goth fades in with reduced motion, and reads on the sheet, the Play View and a troupe's page", async ({ browser }) => {
  const { page, email, handle } = await person(browser, "goth-screens", { reducedMotion: "reduce" });
  makeCustodian(email);
  const headers = { "X-Horatio": "1" };
  const troupeName = `Court of Velvet ${run}`;
  const made = await page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  const id = await builtVampire(page, "Velvetine", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });

  // A short fade to velvet and back, not the curtains.
  await page.goto("/account/preferences");
  await page.getByRole("radiogroup", { name: "Theme" }).getByRole("radio", { name: "Ultra goth" }).click();
  const curtains = page.getByTestId("curtains");
  await expect(curtains.locator(".curtain-fade")).toBeAttached();
  await expect(curtains.locator(".curtain")).toHaveCount(0);
  await expect(curtains).toHaveCount(0, { timeout: 5_000 });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "ultragoth");

  await page.goto(`/characters/${id}`);
  await expect(page.getByRole("heading", { name: "Velvetine" })).toBeVisible();
  await expect(page.getByText("Brawl").first()).toBeVisible();
  await page.screenshot(shots("ultragoth-sheet"));
  await page.goto(`/play/characters/${id}`);
  await expect(page.getByRole("tab", { name: "Tracker" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "ultragoth");
  await page.screenshot(shots("ultragoth-play"));
  await page.getByRole("tab", { name: "Pools" }).click();
  await page.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  await expect(page.getByRole("dialog", { name: "Forms, powers and modifiers" })).toBeVisible();
  await page.screenshot({ path: shots("ultragoth-play-drawer").path });
  await page.goto(`/troupes/${troupeId}`);
  await expect(page.getByRole("heading", { name: troupeName })).toBeVisible();
  await page.screenshot(shots("ultragoth-troupe"));
});

test("the Play View opens as the settings say", async ({ browser }) => {
  const { page } = await person(browser, "play-settings-player");
  // Headless browsers may refuse a wake lock, so this one is a stand-in that grants it.
  await page.context().addInitScript(() => {
    class Lock extends EventTarget {
      released = false;
      async release() {
        this.released = true;
        this.dispatchEvent(new Event("release"));
      }
    }
    Object.defineProperty(navigator, "wakeLock", { value: { request: async () => new Lock() }, configurable: true });
  });
  await page.getByLabel("Name").fill("Mireille");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  const characterId = new URL(page.url()).pathname.split("/")[2]!;

  // As it opens by default: on the Tracker, quick notes on, the screen kept awake.
  await page.goto(`/play/characters/${characterId}`);
  await expect(page.getByRole("tab", { name: "Tracker" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Quick notes")).toBeChecked();
  const awake = page.getByRole("button", { name: "Keep the screen awake" });
  await expect(awake).toHaveAttribute("aria-pressed", "true");
  await expect(awake).toHaveText("☀ Awake");

  // Quick notes off, the screen left to dim, opening on Pools.
  await page.goto("/account/preferences");
  const saved = () => page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.ok());
  for (const label of ["Quick notes", "Keep the screen awake"]) {
    const done = saved();
    await page.getByLabel(label).click();
    await done;
  }
  await expect(page.getByLabel("Quick notes")).not.toBeChecked();
  await expect(page.getByLabel("Keep the screen awake")).not.toBeChecked();
  const done = saved();
  await page.getByRole("radiogroup", { name: "The Play View opens on" }).getByRole("radio", { name: "Pools" }).click();
  await done;

  await page.goto(`/play/characters/${characterId}`);
  await expect(page.getByRole("tab", { name: "Pools" })).toHaveAttribute("aria-selected", "true");
  await expect(awake).toHaveAttribute("aria-pressed", "false");
  await page.screenshot(shots("play-settings"));
  // Choosing the Tracker stays on it, and a spend asks for no note.
  await page.getByRole("tab", { name: "Tracker" }).click();
  await expect(page.getByRole("tab", { name: "Tracker" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Quick notes")).not.toBeChecked();
  await page.getByRole("button", { name: "Spend Willpower", exact: true }).last().click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
