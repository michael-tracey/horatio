import { expect, test, type Locator, type Page } from "@playwright/test";
import { closeContextsAfterEach, makeCustodian, PASSWORD, person } from "./support";

/**
 * The screenshots in docs/manual/getting-started.md (#483), of a fictional player
 * and troupe. Skipped unless MANUAL_SHOTS=1, so CI and the usual runs never take
 * them; run under the e2e lock with
 *   MANUAL_SHOTS=1 ./e2e-local.sh -- e2e/manual-getting-started.spec.ts --project=desktop
 */

closeContextsAfterEach();

test.skip(!process.env.MANUAL_SHOTS, "manual screenshots: run with MANUAL_SHOTS=1");
test.use({ viewport: { width: 1280, height: 900 } });

const DIR = "../docs/manual/images/getting-started";
const headers = { "X-Horatio": "1" };

async function shot(target: Locator, name: string) {
  await target.screenshot({ path: `${DIR}/${name}.png`, animations: "disabled" });
}

/** A clip around several parts of the page at once. */
async function shotAround(page: Page, parts: Locator[], name: string) {
  const boxes = (await Promise.all(parts.map((p) => p.boundingBox()))).filter((b) => b !== null);
  const x = Math.min(...boxes.map((b) => b.x)) - 8;
  const y = Math.min(...boxes.map((b) => b.y)) - 8;
  const right = Math.max(...boxes.map((b) => b.x + b.width)) + 8;
  const bottom = Math.max(...boxes.map((b) => b.y + b.height)) + 8;
  await page.screenshot({ path: `${DIR}/${name}.png`, clip: { x, y, width: right - x, height: bottom - y }, fullPage: true, animations: "disabled" });
}

test("manual: getting started", async ({ browser }, info) => {
  test.skip(info.project.name !== "desktop", "desktop only");
  test.setTimeout(120_000);

  // Signed out: the sign-in page.
  const visitor = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  await visitor.goto("/sign-in");
  await expect(visitor.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await shot(visitor.locator("main"), "sign-in");

  // Signing up, with plain names rather than the suite's run numbers: these shots
  // are taken against a fresh database.
  await visitor.goto("/sign-up");
  await visitor.getByLabel("Your name").fill("Elena Marsh");
  await visitor.getByLabel("Handle").fill("elena_marsh");
  await visitor.getByLabel("Email").fill("elena.marsh@example.com");
  await visitor.getByLabel("Password").fill(PASSWORD);
  await shot(visitor.locator("main section").first(), "sign-up");
  await visitor.getByRole("button", { name: "Create account" }).click();
  await expect(visitor.getByRole("heading", { name: "Your characters" })).toBeVisible();
  const p = visitor;

  // A troupe of her own, asked of the custodian: its answer is in her bell.
  const custodian = await person(browser, "gs-shots-cust");
  makeCustodian(custodian.email);
  const asked = await p.request.post("/api/troupe-requests", {
    headers,
    data: { name: "Court of Ashes", description: "A Camarilla court in a rain-soaked port city." },
  });
  expect(asked.status(), await asked.text()).toBeLessThan(300);
  const approved = await custodian.page.request.post(`/api/troupe-requests/${(await asked.json()).id}/approve`, { headers });
  expect(approved.status(), await approved.text()).toBeLessThan(300);

  // Her profile.
  await p.goto("/account");
  await p.getByLabel("Pronouns").fill("she/her");
  await p.getByLabel("Bio").fill("Playing since the old Laws of the Night days. I like intrigue, court politics and slow-burning plots.");
  await p.getByLabel("Discord username").fill("elenamarsh");
  await p.getByRole("button", { name: "Add a link" }).click();
  await p.getByLabel("Label").fill("Bluesky");
  await p.getByLabel("Address").fill("https://bsky.app/profile/elena.example.com");
  await p.getByRole("button", { name: "Save profile" }).click();
  await expect(p.getByText("Profile saved.")).toBeVisible();
  await expect(p.getByText("Profile saved.")).toBeHidden({ timeout: 15_000 });
  await shot(p.locator("form").filter({ has: p.getByRole("heading", { name: "Profile" }) }), "profile");

  // Settings: how things show.
  await p.goto("/account/settings");
  const card = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  await expect(card("Sheets")).toBeVisible();
  await shotAround(p, [card("Sheets"), card("Dates and times")], "settings");

  // Notifications by email, as on a server that can send it (this suite's can't).
  await p.route("**/api/preferences/email", (route) => route.fulfill({ json: { available: true } }));
  await p.reload();
  await expect(p.getByRole("radiogroup", { name: "Downtime results" })).toBeVisible();
  await shot(card("Notifications by email"), "email-notifications");

  // The bell, with the custodian's answer in it.
  await p.goto("/characters");
  await p.getByRole("button", { name: /^Notifications/ }).click();
  const bell = p.getByRole("dialog", { name: "Notifications" });
  await expect(bell.getByText(/Court of Ashes is ready/)).toBeVisible();
  await shot(bell, "bell");
  await p.keyboard.press("Escape");

  // The calendar link, from the troupe's Games card.
  await p.goto(`/troupes/${(await approved.json()).troupe_id}`);
  await p.getByRole("button", { name: "Subscribe to the calendar" }).click();
  const dialog = p.getByRole("dialog", { name: "Subscribe to the calendar" });
  await dialog.getByRole("region", { name: "Court of Ashes only" }).getByRole("button", { name: "Get the link" }).click();
  await expect(dialog.getByRole("region", { name: "Court of Ashes only" }).getByRole("button", { name: "Copy the link" })).toBeVisible();
  await shot(dialog, "calendar");
});
