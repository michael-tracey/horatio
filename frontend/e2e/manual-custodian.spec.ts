import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";
import { closeContextsAfterEach, makeCustodian, PASSWORD, builtVampire, ATTRIBUTES_AND_FOCUSES, backstoryOptional, topBar } from "./support";

/**
 * The screenshots in the manual's Custodian part (docs/manual/custodian.md), made
 * with a fictional server: a custodian, a few players, troupe requests, an archived
 * troupe and a character to move. Skipped unless MANUAL_SHOTS=1, so CI and the
 * normal e2e runs never take them. From the repository root:
 *
 *   MANUAL_SHOTS=1 HORATIO_BACKUP_DIR="$PWD/.local/manual-backups" \
 *     COMPOSE_PROJECT_NAME=horatio flock /home/michael/git/horatio-work/.e2e.lock \
 *     ./e2e-local.sh -- e2e/manual-custodian.spec.ts --project=desktop
 *
 * HORATIO_BACKUP_DIR turns the Backups tab on; the spec puts a few made-up backups
 * there. The people here have plain names and handles, not the suite's `run`
 * suffix, so the spec needs e2e-local.sh's fresh database each time.
 */

test.skip(!process.env.MANUAL_SHOTS, "manual screenshots: run with MANUAL_SHOTS=1");

closeContextsAfterEach();

const OUT = "../docs/manual/images/custodian";

/** Signs someone up through the sign-up page with a plain handle and email. */
async function signUp(browser: Browser, name: string, handle: string) {
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const email = `${handle.replace(/_/g, ".")}@example.com`;
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill(name);
  await page.getByLabel("Handle").fill(handle);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your characters" })).toBeVisible();
  const me = await (await page.request.get("/api/auth/me")).json();
  return { page, email, handle, id: me.id as string };
}

async function send(p: Page, method: "GET" | "POST" | "PUT", url: string, data?: object) {
  const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
  expect(response.status(), await response.text()).toBeLessThan(300);
  return response.json();
}

/** A PNG of `locator`, or of its top `height` pixels if it is taller. */
async function shoot(locator: Locator, name: string, height?: number) {
  await locator.scrollIntoViewIfNeeded();
  // Let a dialog finish opening.
  await locator.page().waitForTimeout(400);
  const path = `${OUT}/${name}.png`;
  if (!height) return locator.screenshot({ path, animations: "disabled" });
  const box = (await locator.boundingBox())!;
  const scrolled = await locator.page().evaluate(() => window.scrollY);
  return locator.page().screenshot({ path, fullPage: true, animations: "disabled", clip: { x: box.x, y: box.y + scrolled, width: box.width, height: Math.min(box.height, height) } });
}

/** A PNG of the area around all of `locators`, with a margin. */
async function shootAround(page: Page, locators: Locator[], name: string, margin = 8) {
  // Boxes are where things are on screen; a full-page clip is where they are on the page.
  const scrolled = await page.evaluate(() => window.scrollY);
  const boxes = (await Promise.all(locators.map(async (l) => (await l.boundingBox())!))).map((b) => ({ ...b, y: b.y + scrolled }));
  const x = Math.max(0, Math.min(...boxes.map((b) => b.x)) - margin);
  const y = Math.max(0, Math.min(...boxes.map((b) => b.y)) - margin);
  const right = Math.max(...boxes.map((b) => b.x + b.width)) + margin;
  const bottom = Math.max(...boxes.map((b) => b.y + b.height)) + margin;
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true, animations: "disabled", clip: { x, y, width: right - x, height: bottom - y } });
}

test("screenshots for the manual's Custodian part", async ({ browser }) => {
  test.setTimeout(240_000);
  mkdirSync(OUT, { recursive: true });

  const morgan = await signUp(browser, "Morgan Hale", "morgan_hale");
  makeCustodian(morgan.email);
  const tamsin = await signUp(browser, "Tamsin Reyes", "tamsin_reyes");
  const idris = await signUp(browser, "Idris Kerr", "idris_kerr");
  const priya = await signUp(browser, "Priya Lowell", "priya_lowell");
  const jonah = await signUp(browser, "Jonah Ashby", "jonah_ashby");
  const ruth = await signUp(browser, "Ruth Calloway", "ruth_calloway");
  const c = morgan.page;
  await c.reload();

  // Troupe requests: Idris's is approved, Tamsin's waits.
  const harbour = await send(idris.page, "POST", "/api/troupe-requests", {
    name: "Harbour Lights",
    description: "A Camarilla city game on the coast, monthly on Saturdays.",
    note: "About fifteen players, most from our old chronicle.",
  });
  const approved = await send(c, "POST", `/api/troupe-requests/${harbour.id}/approve`);
  await send(tamsin.page, "POST", "/api/troupe-requests", {
    name: "Court of Ashes",
    description: "An Anarch game in the old mill district. Fortnightly, Friday nights.",
    note: "Twelve players so far. I ran the last chronicle's downtimes.",
  });

  // A troupe its lead archived when the chronicle ended.
  const saltmarsh = await send(c, "POST", "/api/troupes", {
    name: "Saltmarsh Court",
    description: "A Sabbat chronicle.",
    lead_handle: jonah.handle,
  });
  await send(jonah.page, "POST", `/api/troupes/${saltmarsh.id}/archive`, { reason: "Our chronicle has ended after six years. Thank you all." });

  // Idris's character, at home in Harbour Lights, to move to Ruth.
  await backstoryOptional(c, approved.troupe_id);
  const corvin = await builtVampire(idris.page, "Corvin Ashe", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const asked = await send(idris.page, "POST", `/api/characters/${corvin}/home-troupe`, { troupe_id: approved.troupe_id });
  await send(c, "POST", `/api/approvals/${asked.id}/approve`, {});

  // People with something going on: a reset link out, and a new email waiting.
  await send(c, "POST", `/api/players/${jonah.id}/password-reset`, { email: false });
  await send(c, "POST", `/api/players/${ruth.id}/email-change`, { email: "ruth.c@example.com", reason: "Lost access to her old address" });

  const main = c.locator("main");
  await (await topBar(c)).getByRole("link", { name: "Custodian", exact: true }).click();

  // Troupe management (#759): a new troupe, the troupes, requests and archived ones.
  await main.getByRole("link", { name: /^Troupe management/ }).click();
  const requests = main.getByRole("region", { name: "Requests" });
  await expect(requests.getByText("Court of Ashes")).toBeVisible();
  await expect(requests.getByText("Harbour Lights")).toBeVisible();
  await shoot(main, "troupe-management");
  await shoot(requests, "troupe-requests");

  const archived = main.getByRole("region", { name: "Archived troupes" });
  await expect(archived.getByText("Our chronicle has ended after six years.", { exact: false })).toBeVisible();
  await shoot(archived, "archived-troupes");

  // Suspend Priya from her row's ⋯.
  await main.getByRole("link", { name: "People", exact: true }).click();
  const table = main.getByRole("table", { name: "People" });
  const row = (name: string) => table.locator("tr").filter({ has: c.getByRole("link", { name, exact: true }) });
  await expect(row("Ruth Calloway")).toBeVisible();
  const choose = async (name: string, item: string) => {
    await row(name).getByRole("button", { name: `Actions for ${name}` }).click();
    await c.getByRole("menu", { name: `Actions for ${name}` }).getByRole("menuitem", { name: item }).click();
  };
  await choose("Priya Lowell", "Suspend…");
  const suspend = c.getByRole("dialog", { name: "Suspend Priya Lowell" });
  await suspend.getByLabel("Reason").fill("Asked to step away for a month after the incident at the last game.");
  await shoot(suspend, "suspend");
  await suspend.getByRole("button", { name: "Suspend Priya Lowell" }).click();
  await expect(suspend).toBeHidden();
  await expect(row("Priya Lowell").getByText("Suspended", { exact: true }).filter({ visible: true })).toBeVisible();

  // The People table, and the ⋯ on a row, without the toast saying she is suspended.
  await c.reload();
  const peopleCard = main.locator("section").first();
  await shoot(peopleCard, "people");
  await row("Tamsin Reyes").getByRole("button", { name: "Actions for Tamsin Reyes" }).click();
  const menu = c.getByRole("menu", { name: "Actions for Tamsin Reyes" });
  await expect(menu).toBeVisible();
  await shootAround(c, [table, menu], "people-menu");

  // Reset a password.
  await menu.getByRole("menuitem", { name: "Reset password…" }).click();
  const reset = c.getByRole("dialog", { name: "Reset Tamsin Reyes's password" });
  await reset.getByRole("button", { name: "Make a reset link" }).click();
  await expect(reset.getByLabel("Reset link", { exact: true })).toBeVisible();
  await shoot(reset, "reset-password");
  await reset.getByRole("button", { name: "Close" }).click();

  // Move Idris's character to Ruth, up to the confirmation.
  await choose("Idris Kerr", "Characters");
  const characters = c.getByRole("dialog", { name: "Idris Kerr's characters" });
  await characters.getByRole("button", { name: "Move Corvin Ashe to another player" }).click();
  const move = c.getByRole("dialog", { name: "Move Corvin Ashe to another player" });
  await move.getByLabel("New player").fill(ruth.handle);
  await move.getByRole("listbox", { name: "People" }).getByRole("option", { name: `@${ruth.handle}` }).click();
  await move.getByLabel("Reason").fill("Idris has handed the character on to Ruth, with the storytellers' blessing.");
  await move.getByRole("button", { name: "Continue" }).click();
  await expect(move.getByText("Its sheet, XP, history, titles and status go with it.")).toBeVisible();
  await shoot(move, "move-character");
  await move.getByRole("button", { name: "Back" }).click();
  await move.getByRole("button", { name: "Cancel" }).click();
  await characters.getByRole("button", { name: "Close" }).click();

  // The cards under the table: suspended, password resets and email changes.
  const card = (title: string) => main.locator("section", { has: c.getByRole("heading", { name: title, exact: true }) });
  await card("Email changes").scrollIntoViewIfNeeded();
  await shootAround(c, [card("Suspended"), card("Password resets"), card("Email changes")], "people-cards", 0);

  // Backups, with a few made up beside a nightly one or two.
  const backupDir = process.env.HORATIO_BACKUP_DIR;
  if (backupDir) {
    mkdirSync(backupDir, { recursive: true });
    const day = 24 * 60 * 60 * 1000;
    const stamp = (at: Date) => at.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
    const today = new Date();
    today.setUTCHours(8, 17, 4, 0);
    for (let i = 1; i <= 4; i++) writeFileSync(join(backupDir, `horatio-${stamp(new Date(today.getTime() - i * day))}.sql.gz`), Buffer.alloc(2_400_000 + i * 21_000));
    writeFileSync(join(backupDir, `horatio-${stamp(new Date(today.getTime() - 2 * day + 5 * 60 * 60 * 1000))}-manual.sql.gz`), Buffer.alloc(2_430_000));
    await main.getByRole("link", { name: "Backups", exact: true }).click();
    await expect(main.getByText("Made here", { exact: true })).toBeVisible();
    await shoot(main, "backups");
  }

  // The Settings tab: the loading animation, each caught mid-way rather than at its start.
  await main.getByRole("link", { name: "Settings", exact: true }).click();
  const settings = main.locator("section", { has: c.getByRole("heading", { name: "Loading animation" }) });
  await expect(settings.locator(".loader-block")).toHaveCount(4);
  await c.waitForTimeout(400);
  await c.evaluate(() =>
    document.getAnimations().forEach((a) => {
      a.pause();
      a.currentTime = 1100;
    }),
  );
  await settings.screenshot({ path: `${OUT}/settings.png` });

  // The System tab.
  await main.getByRole("link", { name: "System", exact: true }).click();
  await expect(main.getByText("What is running")).toBeVisible();
  await shoot(main, "system");

  // The audit log.
  await main.getByRole("link", { name: "Audit", exact: true }).click();
  await expect(main.getByRole("list", { name: "Audit log" })).toBeVisible();
  await shoot(main.locator("section", { has: c.getByRole("heading", { name: "Found" }) }), "audit", 520);

  // Importing from Yorick: the made-up page from the backend's tests, checked by a dry run.
  await main.getByRole("link", { name: "Tools", exact: true }).click();
  await main.getByRole("link", { name: "Open the import" }).click();
  await main.getByLabel("Troupe").selectOption({ label: "Harbour Lights" });
  await main.getByLabel("Print Characters page").setInputFiles({
    name: "Print Troupe Characters.html",
    mimeType: "text/html",
    buffer: readFileSync("../backend/tests/fixtures/yorick_print.html"),
  });
  await expect(main.getByText(/^3 characters read from the page/)).toBeVisible({ timeout: 30_000 });
  await shoot(main, "yorick-import", 1400);
});
