import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";
import { ATTRIBUTES_AND_FOCUSES, PASSWORD, backstoryOptional, builtVampire, closeContextsAfterEach, makeCustodian } from "./support";

/**
 * The screenshots for the manual's Running a troupe part (docs/manual/running-a-troupe.md,
 * issue #483). Never run by CI or a normal e2e run: only with MANUAL_SHOTS=1, on the
 * desktop project, against the fresh database ./e2e-local.sh makes, since its people
 * and troupe have plain names a second run in the same database would clash with:
 *
 *   MANUAL_SHOTS=1 COMPOSE_PROJECT_NAME=horatio flock /home/michael/git/horatio-work/.e2e.lock \
 *     ./e2e-local.sh -- e2e/manual-running-a-troupe.spec.ts --project=desktop
 *
 * Everyone and everything in them is made up.
 */

test.skip(!process.env.MANUAL_SHOTS, "manual screenshots: run with MANUAL_SHOTS=1");

closeContextsAfterEach();

const OUT = "../docs/manual/images/running-a-troupe";
const headers = { "X-Horatio": "1" };

/** Someone signed up with a plain name and handle, for the pictures: not `run`'s. */
async function member(browser: Browser, name: string, handle: string): Promise<{ page: Page; email: string; handle: string }> {
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const email = `${handle}@example.com`;
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill(name);
  await page.getByLabel("Handle").fill(handle);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your characters" })).toBeVisible();
  return { page, email, handle };
}

async function send(page: Page, method: "GET" | "POST" | "PUT" | "PATCH", url: string, data?: object) {
  const response = await page.request.fetch(url, { method, headers, data });
  expect(response.status(), `${method} ${url}: ${await response.text()}`).toBeLessThan(300);
  return response.json();
}

/** The e2e server's address, where a picture shows it, as a site's would read. */
async function plainHost(page: Page) {
  await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.nodeValue?.includes(location.host)) node.nodeValue = node.nodeValue.replaceAll(location.host, "horatio.example.org");
    }
  });
}

/** A picture of `area` (the page's main part by default), cut off below `most` pixels. */
async function shot(page: Page, name: string, area?: Locator, most = 1000) {
  await page.waitForLoadState("networkidle");
  // Toasts and the like settle before the picture.
  await page.waitForTimeout(300);
  const target = area ?? page.locator("main");
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  if (!box) throw new Error(`Nothing to picture for ${name}`);
  const scroll = await page.evaluate(() => window.scrollY);
  await page.screenshot({
    path: `${OUT}/${name}.png`,
    fullPage: true,
    clip: { x: Math.max(0, box.x - 8), y: Math.max(0, box.y + scroll - 8), width: Math.min(1280, box.width + 16), height: Math.min(most, box.height + 16) },
  });
}

/** A card on the page, by its heading. */
const card = (page: Page, heading: string) => page.locator("section").filter({ has: page.getByRole("heading", { name: heading, exact: true }) }).first();

test("screenshots for Running a troupe", async ({ browser }) => {
  test.skip(test.info().project.name !== "desktop", "desktop only");
  test.setTimeout(600_000);

  // The people: the custodian, the troupe's staff, and four players.
  const custodian = await member(browser, "Site Custodian", "custodian");
  makeCustodian(custodian.email);
  await custodian.page.reload();
  const lead = await member(browser, "Mira Castellane", "mira");
  const storyteller = await member(browser, "Tomas Reyes", "tomas");
  const assistant = await member(browser, "Ines Calder", "ines");
  const narrator = await member(browser, "Oren Pike", "oren");
  const lucia = await member(browser, "Lucia Bram", "lucia");
  const dev = await member(browser, "Dev Okafor", "dev");
  const sasha = await member(browser, "Sasha Lind", "sasha");
  const noor = await member(browser, "Noor Haddad", "noor");
  const l = lead.page;

  // The troupe, its staff and its profile.
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: "Court of Ashes", lead_handle: lead.handle });
  const base = `/troupes/${troupeId}`;
  await backstoryOptional(l, troupeId);
  await send(l, "PATCH", `/api/troupes/${troupeId}`, {
    description: "A Camarilla chronicle in a rain-soaked port city, where the old Prince's grip is slipping and every clan is counting favours.",
  });
  await send(l, "PUT", `/api/troupes/${troupeId}/profile`, {
    schedule: "Second Saturday of the month, 7 pm to midnight",
    content_notes: "",
    links: {},
    setting: { chronicle: "The Drowned Crown", city: "Port Halden", era: "Modern nights", tone: "Political, slow-burning" },
    venue: { name: "The Lantern Rooms", region: "Port Halden", address: "", access: "Step-free access" },
    new_players: "welcoming",
  });
  await send(l, "PUT", `/api/troupes/${troupeId}/staff`, { handle: storyteller.handle, role: "storyteller" });
  await send(l, "PUT", `/api/troupes/${troupeId}/staff`, { handle: assistant.handle, role: "assistant_storyteller" });
  await send(l, "PUT", `/api/troupes/${troupeId}/staff`, { handle: narrator.handle, role: "narrator" });

  // Three characters call the troupe home; a fourth asks to.
  const build = (backgrounds: [string, number][], disciplines: [string, number][]) => ({ ...ATTRIBUTES_AND_FOCUSES, backgrounds, disciplines });
  const celestine = await builtVampire(lucia.page, "Celestine Marrow", "Toreador", build([["Fame", 3], ["Resources", 2], ["Generation", 1]], [["Auspex", 2], ["Celerity", 1], ["Presence", 1]]));
  const ezra = await builtVampire(dev.page, "Ezra Vale", "Brujah", build([["Fame", 3], ["Herd", 2], ["Generation", 1]], [["Celerity", 2], ["Potence", 1], ["Presence", 1]]));
  const wren = await builtVampire(sasha.page, "Wren Halloway", "Brujah", build([["Allies", 3], ["Haven", 2], ["Generation", 1]], [["Celerity", 2], ["Potence", 1], ["Presence", 1]]));
  const hollis = await builtVampire(noor.page, "Hollis Crane", "Nosferatu", build([["Contacts", 3], ["Haven", 2], ["Generation", 1]], [["Animalism", 2], ["Obfuscate", 1], ["Potence", 1]]));
  for (const [page, id] of [
    [lucia.page, celestine],
    [dev.page, ezra],
    [sasha.page, wren],
  ] as const) {
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
    await send(l, "POST", `/api/approvals/${asked.id}/approve`, {});
  }
  await send(noor.page, "POST", `/api/characters/${hollis}/home-troupe`, { troupe_id: troupeId });

  // NPCs: the Prince and her Sheriff, sheeted, and a Stock informant.
  for (const [name, clan, title] of [
    ["Aurelia Vance", "Ventrue", "Prince"],
    ["Dane Kessler", "Brujah", "Sheriff"],
  ] as const) {
    const npc = await send(l, "POST", `/api/troupes/${troupeId}/npcs`, { name, wizard: false });
    await send(l, "PUT", `/api/characters/${npc.id}/npc/ratings`, { category: "sect", name: "Camarilla", rating: null, detail: "" });
    await send(l, "PUT", `/api/characters/${npc.id}/npc/ratings`, { category: "clan", name: clan, rating: null, detail: "" });
    await send(l, "PUT", `/api/troupes/${troupeId}/characters/${npc.id}/titles`, { titles: [title] });
  }
  await send(l, "POST", `/api/troupes/${troupeId}/npcs`, {
    name: "Dockside Informant",
    npc_kind: "mortal",
    npc_form: "stock",
    stock: { rating: 2, specializations: [{ type: "skill", name: "Streetwise" }], notes: "Sells what he hears on the wharf." },
  });

  // Two checks played differently.
  const checks: { key: string; message: string; about: string }[] = await send(l, "GET", `/api/troupes/${troupeId}/checks`);
  const played = checks.filter((c) => c.message && c.about !== "any").slice(0, 2);
  for (const [i, c] of played.entries()) await send(l, "PUT", `/api/troupes/${troupeId}/checks/${c.key}`, { strength: i === 0 ? "review" : "note" });

  // Games: one under way, one next month.
  // On the hour, as games are: this one began between half an hour and an hour and a half ago.
  const start = new Date(Date.now() - 30 * 60_000);
  start.setMinutes(0, 0, 0);
  const { id: gameId } = await send(l, "POST", `/api${base}/games`, { starts_at: start.toISOString(), ends_at: new Date(start.getTime() + 5 * 60 * 60_000).toISOString() });
  const next = new Date(Date.now() + 30 * 86_400_000);
  next.setHours(19, 0, 0, 0);
  await send(l, "POST", `/api${base}/games`, { starts_at: next.toISOString(), ends_at: new Date(next.getTime() + 5 * 60 * 60_000).toISOString() });

  // A downtime cycle, open, with two downtimes in.
  const now = Date.now();
  const cycle = await send(l, "POST", `/api${base}/cycles`, {
    name: "Harvest Moon",
    closes_at: new Date(now + 7 * 86_400_000).toISOString(),
    grace_ends_at: new Date(now + 9 * 86_400_000).toISOString(),
    completion_xp: 2,
  });
  await send(l, "POST", `/api/cycles/${cycle.id}/open`);
  const errands: [Page, string, string[]][] = [
    [lucia.page, celestine, ["Host a salon for the Harpies and listen for talk of the Prince's health.", "Commission a portrait of the Sheriff, to learn who sits for him."]],
    [dev.page, ezra, ["Walk the docks with my herd and find out who is buying up the warehouses.", "Train with the anarch crew at the boxing gym."]],
  ];
  for (const [page, id, bodies] of errands) {
    const form = await send(page, "GET", `/api/characters/${id}/downtime`);
    const question = form.questions.find((q: { prompt: string }) => q.prompt === "Downtime action");
    await send(page, "PUT", `/api/characters/${id}/downtime/answers`, { answers: bodies.map((body, i) => ({ question_id: question.id, slot: i + 1, body })) });
    await send(page, "POST", `/api/characters/${id}/downtime/submit`);
  }
  const responses: { id: string; character_name: string }[] = await send(l, "GET", `/api/cycles/${cycle.id}/responses`);
  const staffList: { user_id: string; handle: string }[] = await send(l, "GET", `/api${base}/staff`);
  const oren = staffList.find((s) => s.handle === narrator.handle)!.user_id;
  const ezras = responses.filter((r) => r.character_name === "Ezra Vale").map((r) => r.id);
  await send(l, "PUT", `/api/cycles/${cycle.id}/responses/assignment`, { response_ids: ezras, any_narrator: false, user_id: oren });
  const celestines = responses.filter((r) => r.character_name === "Celestine Marrow").map((r) => r.id);
  await send(l, "PUT", `/api/cycles/${cycle.id}/responses/assignment`, { response_ids: celestines.slice(0, 1), any_narrator: true });
  await send(l, "PUT", `/api/responses/${celestines[0]}`, { body: "The Harpies whisper that the Prince has not fed in public for a month." });

  // About, for the lead: what waits on her, the games, and who may join.
  await l.goto(base);
  await expect(l.getByRole("list", { name: "Waiting on you" })).toBeVisible();
  await expect(l.getByRole("list", { name: "Games to come" })).toBeVisible();
  await shot(l, "about", undefined, 1100);

  // Staff.
  await l.goto(`${base}/staff`);
  await expect(l.getByText("Oren Pike")).toBeVisible();
  await shot(l, "staff", undefined, 900);

  // Customise › Overview.
  await l.goto(`${base}/customise`);
  await expect(l.getByRole("list", { name: "Setting up" })).toBeVisible();
  await shot(l, "customise-overview", undefined, 1100);

  // The Characters list, with the print choices open.
  await l.goto(`${base}/characters`);
  await expect(l.getByRole("link", { name: "Celestine Marrow" })).toBeVisible();
  await l.getByLabel("Select Celestine Marrow").check();
  await l.getByLabel("Select Ezra Vale").check();
  await l.getByRole("button", { name: /^Print…/ }).click();
  await shot(l, "characters", undefined, 900);

  // NPCs, with the New NPC form.
  await l.goto(`${base}/npcs`);
  await expect(l.getByRole("row", { name: "Aurelia Vance" })).toBeVisible();
  await shot(l, "npcs", undefined, 900);

  // Rules › Checks, on the troupe's house rules.
  await l.goto(`${base}/rules`);
  await expect(l.getByRole("button", { name: /^House rules \(2\)/ })).toBeVisible();
  await shot(l, "rules-checks", undefined, 1200);

  // A check of the troupe's own being built.
  await l.getByRole("button", { name: "Add a check" }).click();
  const form = l.getByRole("region", { name: "A new check" });
  await form.getByLabel("Kind of trait", { exact: true }).selectOption({ label: "Merits" });
  await form.getByLabel("Trait", { exact: true }).selectOption("Iron Will");
  await form.getByLabel("It", { exact: true }).selectOption({ label: "Is allowed only when…" });
  await form.getByLabel("Condition: add a block").selectOption({ label: "Clan or its bloodlines…" });
  await form.getByLabel("Condition 1: add a trait").selectOption("Ventrue");
  await form.getByLabel("Message the player sees").fill("Iron Will is for the Ventrue here.");
  await expect(form.getByRole("region", { name: "Preview" })).toContainText("Iron Will: refused unless the clan is Ventrue");
  await shot(l, "own-check", form, 1200);

  // Rules › Book traits: a merit banned, with the troupe's wording.
  await l.goto(`${base}/rules/book-traits`);
  await l.getByRole("searchbox", { name: "Search book traits" }).fill("lucky");
  await l.getByRole("list", { name: "Book traits found" }).getByRole("button", { name: /^Lucky/ }).click();
  await l.getByLabel("Banned in this troupe").check();
  await l.getByLabel("Reason (optional)").fill("Too swingy at our table.");
  await l.getByLabel("House wording").fill("Here, Lucky's retest can't be used on a test to resist a Discipline.");
  const panel = card(l, "Lucky");
  await shot(l, "book-trait", panel, 1200);

  // Approvals: Hollis asks to make the troupe home.
  await l.goto(`${base}/approvals`);
  const asking = l.locator("section").filter({ hasText: "Hollis Crane" }).first();
  await expect(asking).toContainText("Asking to make this home");
  await shot(l, "approvals", undefined, 1100);

  // The cycle's Overview, and its Responses.
  await l.goto(`/cycles/${cycle.id}`);
  await expect(l.getByText("2 of 3 submitted")).toBeVisible();
  await shot(l, "cycle", undefined, 900);
  await l.goto(`/cycles/${cycle.id}/responses`);
  await expect(l.getByRole("region", { name: "Ezra Vale" })).toBeVisible();
  await shot(l, "responses", undefined, 1100);

  // Game night: check-in open, two characters in.
  await send(l, "PUT", `/api${base}/games/${gameId}/checkin`);
  for (const id of [celestine, ezra]) await send(l, "POST", `/api${base}/games/${gameId}/attendance`, { character_id: id });
  await l.goto(`${base}/games/${gameId}`);
  await expect(l.getByRole("table", { name: "Checked in" })).toBeVisible();
  await plainHost(l);
  await shot(l, "game-night", undefined, 1000);

  // Characters › Award XP, ready to award.
  await l.goto(`${base}/xp`);
  await l.getByLabel("Note everyone gets").fill("Game, the Harvest Ball");
  await l.getByRole("button", { name: "Less XP for Wren Halloway" }).click();
  await shot(l, "award-xp", undefined, 900);

  // Troupe settings › Game XP chart, being changed to a taper.
  await l.goto(`${base}/settings`);
  await l.getByRole("button", { name: "Change the game XP chart" }).click();
  const chart = card(l, "Game XP chart");
  await chart.getByRole("group", { name: "Start from a preset" }).getByRole("button").nth(1).click();
  await shot(l, "game-xp-chart", chart, 1300);
});
