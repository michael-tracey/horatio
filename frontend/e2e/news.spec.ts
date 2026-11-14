import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { ATTRIBUTES_AND_FOCUSES, backstoryOptional, builtVampire, closeContextsAfterEach, makeCustodian, person, run, shots } from "./support";

/** Troupe news (#510): storytellers write as the troupe's news agencies, schedule a story, and its players read it when it goes out. */

closeContextsAfterEach();

const NEONATE = {
  ...ATTRIBUTES_AND_FOCUSES,
  backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][],
  disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][],
};

async function send(page: Page, method: "POST" | "PUT", url: string, data: object) {
  const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
  expect(response.status(), await response.text()).toBeLessThan(300);
  return response.json();
}

/** The troupe's tabs: on a phone, the open group's own row of tabs. */
const troupeTab = (page: Page, name: RegExp) => page.locator("main").getByRole("link", { name });

test("news: a storyteller makes an agency and schedules a story, it goes out, and a player reads it with its unread dot", async ({ browser }) => {
  // The story goes out on the delivery worker's first round after its minute.
  test.setTimeout(300_000);
  const custodian = await person(browser, "newsdesk-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "newsdesk-lead");
  const player = await person(browser, "newsdesk-reader");
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Evening Gazette Court ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const id = await builtVampire(player.page, "Ottoline", "Brujah", NEONATE);
  const asked = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});

  // The lead makes an agency under Customise › News agencies.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/news-agencies`);
  await l.getByRole("button", { name: "Add an agency" }).click();
  const dialog = l.getByRole("dialog", { name: "Add an agency" });
  await dialog.getByLabel("Name").fill("The Evening Gazette");
  await dialog.getByLabel("Description (optional)").fill("The city's late paper.");
  await dialog.getByRole("button", { name: "Add the agency" }).click();
  await expect(l.getByRole("table", { name: "News agencies" }).getByText("The Evening Gazette", { exact: true })).toBeVisible();
  // No Discord server: news is in the app only, and the page says so.
  await expect(l.getByText(/News is in the app only until a Discord server is connected/)).toBeVisible();

  // It writes a story on the News tab and schedules it for the next minute.
  await l.goto(`/troupes/${troupe.id}`);
  await troupeTab(l, /^News(?! agencies)/).click();
  await l.getByRole("link", { name: "News desk" }).click();
  await l.getByRole("link", { name: "Write a story" }).click();
  // The only agency is chosen already.
  await expect(l.getByLabel("Agency")).toHaveValue(/.+/);
  await l.getByLabel("Headline").fill("Fire at the harbour warehouses");
  await l.getByLabel("Dateline (optional)").fill("Boston, the night of the 3rd");
  const editor = l.getByRole("textbox", { name: "The story", exact: true });
  await editor.click();
  await l.keyboard.type("Smoke rose over the harbour until dawn. Nobody saw who lit it.");
  await l.getByRole("button", { name: "Preview" }).click();
  await expect(l.getByRole("heading", { name: "Fire at the harbour warehouses" })).toBeVisible();
  await expect(l.getByLabel("On Discord")).toContainText("Read in Horatio");
  await l.getByRole("button", { name: "Write", exact: true }).click();
  await l.getByRole("button", { name: "Schedule…" }).click();
  // The next minute at least 20 seconds away, on the browser's own clock.
  const when = await l.evaluate(() => {
    const at = new Date(Date.now() + 20_000);
    at.setSeconds(0, 0);
    at.setMinutes(at.getMinutes() + 1);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
  });
  await l.getByLabel(/^Publish at/).fill(when);
  await l.getByRole("button", { name: "Schedule", exact: true }).click();
  await expect(l.getByRole("heading", { name: "Scheduled" })).toBeVisible();
  await expect(l.getByText(/^Goes out /)).toBeVisible();
  await expect(l.getByText("In the app only: Discord isn't set up on this server.")).toBeVisible();

  // Before its time, the player sees nothing; once the worker has published it, it's there, unread.
  const p = player.page;
  await p.goto(`/troupes/${troupe.id}/news`);
  await expect(p.getByText("No stories yet.")).toBeVisible();
  const story = p.getByRole("link", { name: /^Unread: Fire at the harbour warehouses, from The Evening Gazette/ });
  await expect(async () => {
    await p.reload();
    await expect(story).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 200_000, intervals: [5_000] });
  await expect(troupeTab(p, /^News 1 unread$/)).toBeVisible();
  await expect(story).toContainText("Boston, the night of the 3rd");
  await p.screenshot(shots("news-list"));

  // Opening it reads it: the whole story, and the dot and count go.
  await story.click();
  await expect(p.getByRole("heading", { name: "Fire at the harbour warehouses" })).toBeVisible();
  await expect(p.getByText("Smoke rose over the harbour until dawn. Nobody saw who lit it.")).toBeVisible();
  await expect(p.getByText(/^Published /)).toBeVisible();
  await p.screenshot(shots("news-story"));
  await p.getByRole("link", { name: "All news" }).click();
  await expect(p.getByRole("link", { name: /^Fire at the harbour warehouses, from The Evening Gazette/ })).toBeVisible();
  await expect(troupeTab(p, /^News$/)).toBeVisible();

  // The troupe's front page has the latest headline.
  await troupeTab(p, /^Overview$/).click();
  await expect(p.getByRole("heading", { name: "Latest news" })).toBeVisible();
  await expect(p.getByRole("link", { name: /Fire at the harbour warehouses/ })).toBeVisible();
});

test("an agency's portrait: a storyteller uploads and crops it, and it shows beside the masthead (#883)", async ({ browser }) => {
  const custodian = await person(browser, "herald-desk-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "herald-desk-lead");
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Herald Portrait Court ${run}`, lead_handle: lead.handle });
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/agencies`, { name: "The Crimson Herald" });

  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/news-agencies`);
  await l.getByRole("button", { name: "Actions for The Crimson Herald" }).click();
  await l.getByRole("menuitem", { name: "Portrait…" }).click();
  const dialog = l.getByRole("dialog", { name: "The Crimson Herald's portrait" });
  await expect(dialog.getByText(/its stories show on Discord beside its name/)).toBeVisible();
  await dialog.getByLabel("Choose a portrait").setInputFiles("e2e/portrait.jpg");
  await expect(dialog.getByRole("slider", { name: /Where the portrait is/ })).toBeVisible();
  await dialog.getByRole("button", { name: "Save picture" }).click();
  await expect(dialog.locator('img[src*="/portraits/"]')).toHaveAttribute("src", /\/api\/agencies\/.+\/portraits\/.+\/512\.webp$/);
  await expect(dialog.getByRole("button", { name: "Move the crop" })).toBeVisible();
  await l.keyboard.press("Escape");

  // Beside its masthead in the list, and in the troupe's log.
  const row = l.getByRole("table", { name: "News agencies" }).getByRole("row").filter({ hasText: "The Crimson Herald" });
  await expect(row.locator('img[src*="/portraits/"]')).toHaveJSProperty("complete", true);
  await l.goto(`/troupes/${troupe.id}/log`);
  await expect(l.getByText("changed the portrait of the news agency The Crimson Herald.")).toBeVisible();
});

test("announcements: a storyteller pins one, a player sees its banner, dismisses it, and reads it under Announcements, never under News", async ({ browser }) => {
  const custodian = await person(browser, "noticeboard-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "noticeboard-lead");
  const player = await person(browser, "noticeboard-reader");
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Notice Board Court ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const id = await builtVampire(player.page, "Philippa", "Brujah", NEONATE);
  const asked = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});

  // The lead writes one on the Announcements tab, pinned for two days, and publishes it.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}`);
  await troupeTab(l, /^Announcements/).click();
  await l.getByRole("link", { name: "Announcements desk" }).click();
  await l.getByRole("link", { name: "Write an announcement" }).click();
  await expect(l.getByLabel("Agency")).toHaveCount(0);
  await l.getByLabel("Title").fill("New venue parking");
  await l.getByRole("textbox", { name: "The announcement", exact: true }).click();
  await l.keyboard.type("Park in the back lot off Elm Street from this game on.");
  await expect(l.getByText(/Emails everyone in the troupe as it's published/)).toBeVisible();
  const day = await l.evaluate(() => {
    const at = new Date(Date.now() + 2 * 86_400_000);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`;
  });
  await l.getByLabel(/^Pin to the front page until/).fill(day);
  await l.getByRole("button", { name: "Publish now" }).click();
  await expect(l.getByRole("heading", { name: "New venue parking" })).toBeVisible();
  await expect(l.getByText("noticeboard-lead, Lead storyteller")).toBeVisible();

  // The player sees its banner on the troupe's front page, and dismisses it.
  const p = player.page;
  await p.goto(`/troupes/${troupe.id}`);
  const banners = p.getByRole("list", { name: "Pinned announcements" });
  await expect(banners.getByRole("link", { name: "New venue parking" })).toBeVisible();
  await expect(banners).toContainText("noticeboard-lead, Lead storyteller");
  await p.screenshot(shots("announcement-banner"));
  await banners.getByRole("button", { name: "Dismiss “New venue parking”" }).click();
  await expect(p.getByRole("list", { name: "Pinned announcements" })).toHaveCount(0);

  // Not under News; under Announcements, pinned first and unread, until opened.
  await troupeTab(p, /^News(?! agencies)/).click();
  await expect(p.getByText("No stories yet.")).toBeVisible();
  await troupeTab(p, /^Announcements 1 unread$/).click();
  const notice = p.getByRole("link", { name: /^Unread: Pinned: New venue parking, from noticeboard-lead, Lead storyteller/ });
  await expect(notice).toBeVisible();
  await notice.click();
  await expect(p.getByRole("heading", { name: "New venue parking" })).toBeVisible();
  await expect(p.getByText("Park in the back lot off Elm Street from this game on.")).toBeVisible();
  await p.screenshot(shots("announcement"));
  await p.getByRole("link", { name: "All announcements" }).click();
  await expect(p.getByRole("link", { name: /^Pinned: New venue parking/ })).toBeVisible();
  await expect(troupeTab(p, /^Announcements$/)).toBeVisible();
  // Dismissed for them only: the banner is gone from the front page for good.
  await troupeTab(p, /^Overview$/).click();
  await expect(p.getByRole("heading", { name: "Who may join" })).toBeVisible();
  await expect(p.getByRole("list", { name: "Pinned announcements" })).toHaveCount(0);
});

test("an announcement's picture shows as a thumbnail on its pinned banner, in the list and in the bell (#832)", async ({ browser }) => {
  const custodian = await person(browser, "thumbs-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "thumbs-lead");
  const player = await person(browser, "thumbs-reader");
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Thumbnail Court ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const id = await builtVampire(player.page, "Odalys", "Brujah", NEONATE);
  const asked = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});

  // A pinned announcement with a picture, and one without.
  const pinnedUntil = new Date(Date.now() + 2 * 86_400_000).toISOString();
  const pictured = await send(lead.page, "POST", `/api/troupes/${troupe.id}/posts`, { kind: "announcement", title: "Masquerade ball", body: "Masks at the door.", pinned_until: pinnedUntil });
  const picture = await lead.page.request.post(`/api/posts/${pictured.id}/picture`, {
    headers: { "X-Horatio": "1" },
    multipart: { file: { name: "ball.jpg", mimeType: "image/jpeg", buffer: readFileSync("e2e/portrait.jpg") } },
  });
  expect(picture.status(), await picture.text()).toBe(200);
  await send(lead.page, "POST", `/api/posts/${pictured.id}/publish`, {});
  const plain = await send(lead.page, "POST", `/api/troupes/${troupe.id}/posts`, { kind: "announcement", title: "Bring a chair", body: "Seats are short.", pinned_until: pinnedUntil });
  await send(lead.page, "POST", `/api/posts/${plain.id}/publish`, {});

  // On the front page's banners: a thumbnail beside the one with a picture only.
  const p = player.page;
  await p.goto(`/troupes/${troupe.id}`);
  const banners = p.getByRole("list", { name: "Pinned announcements" });
  await expect(banners.getByRole("link", { name: "Bring a chair" })).toBeVisible();
  const ball = banners.getByRole("listitem").filter({ hasText: "Masquerade ball" });
  await expect(ball.locator("img")).toHaveAttribute("src", /\/post-pictures\/.+\/600\.webp$/);
  await expect(ball.locator("img")).toHaveJSProperty("complete", true);
  await expect(banners.getByRole("listitem").filter({ hasText: "Bring a chair" }).locator("img")).toHaveCount(0);

  // In the list, beside its byline.
  await troupeTab(p, /^Announcements/).click();
  await expect(p.getByRole("link", { name: /Masquerade ball/ }).locator("img")).toHaveCount(1);
  await expect(p.getByRole("link", { name: /Bring a chair/ }).locator("img")).toHaveCount(0);

  // And in the bell.
  await p.getByRole("button", { name: /^Notifications/ }).click();
  const bell = p.getByRole("dialog", { name: "Notifications" });
  await expect(bell.getByRole("button", { name: /Announcement: Masquerade ball/ }).locator("img")).toHaveAttribute("src", /\/600\.webp$/);
  await expect(bell.getByRole("button", { name: /Announcement: Bring a chair/ }).locator("img")).toHaveCount(0);
});
