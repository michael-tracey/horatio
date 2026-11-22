import { expect, test, type Page } from "@playwright/test";
import { ATTRIBUTES_AND_FOCUSES, backstoryOptional, builtVampire, closeContextsAfterEach, creatingVampire, makeCustodian, person, run, shots } from "./support";

/**
 * No screen is wider than a phone (#923). A player, a narrator and a storyteller who is
 * the custodian too walk every screen they can reach through its tabs, on a 375px
 * screen, and each screen must fit it with nothing to scroll sideways: once as it
 * opens, and again with everything folded away opened. A table or a row of tabs may
 * scroll inside itself; the page may not.
 */
closeContextsAfterEach();

// The narrowest phone in common use, narrower than the phone project's own.
const viewport = { width: 375, height: 800 };
const headers = { "X-Horatio": "1" };

// Screens known to be too wide, each waiting on its own ticket: the address, with "ID" for each id.
const KNOWN: string[] = [];

async function send(page: Page, method: "GET" | "POST" | "PUT" | "PATCH", url: string, data?: object) {
  const response = await page.request.fetch(url, { method, headers, data });
  expect(response.status(), `${method} ${url}: ${await response.text()}`).toBeLessThan(300);
  return response.json().catch(() => ({}));
}

/**
 * How far the page reaches past the screen's right edge, and the widest thing that takes it there.
 * Against the screen's own width: an emulated phone's layout viewport can widen to fit what is
 * too wide, taking `innerWidth` and the like with it (#914).
 */
function overflow(page: Page) {
  return page.evaluate((width) => {
    const over = document.documentElement.scrollWidth - width;
    if (over <= 0) return null;
    // Inside something that scrolls or clips sideways, it doesn't widen the page.
    const contained = (el: Element) => {
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(p).overflowX)) return true;
      return false;
    };
    let widest: { el: Element; right: number } | null = null;
    for (const el of Array.from(document.body.querySelectorAll("*"))) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height || r.right <= width + 1 || contained(el)) continue;
      // The outermost of the widest: its own children reach no further.
      if (!widest || r.right > widest.right + 1 || (Math.abs(r.right - widest.right) <= 1 && el.contains(widest.el))) widest = { el, right: r.right };
    }
    const el = widest?.el;
    const what = el ? `<${el.tagName.toLowerCase()} class="${(el.getAttribute("class") ?? "").slice(0, 80)}"> "${(el.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 40)}"` : "nothing found";
    return `${over}px too wide; widest: ${what}, right edge at ${Math.round(widest?.right ?? 0)}px`;
  }, page.viewportSize()!.width);
}

/** The address with each id as "ID", to name a screen the same on every run. */
const screen = (url: string) => url.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, "ID");

/**
 * Opens a screen and checks it fits, as it opens and with every fold opened. Gives
 * the addresses its tabs lead to: the rows, and on a phone the section pickers'
 * sheets (#904), which hold their links only while open.
 */
async function visit(page: Page, who: string, url: string, wide: string[]): Promise<string[]> {
  await page.goto(url);
  await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(300);
  const name = `${who} ${screen(url)}`;
  if (KNOWN.includes(screen(url))) return links(page);
  const closed = await overflow(page);
  if (closed) wide.push(`${name}: ${closed}`);
  const folds = await page.evaluate(() => {
    const shut = Array.from(document.querySelectorAll("main details:not([open])"));
    shut.forEach((d) => ((d as HTMLDetailsElement).open = true));
    return shut.length;
  });
  if (folds && !closed) {
    await page.waitForLoadState("networkidle", { timeout: 3000 }).catch(() => {});
    await page.waitForTimeout(200);
    const open = await overflow(page);
    if (open) wide.push(`${name}, its folds open: ${open}`);
  }
  return links(page);
}

async function links(page: Page): Promise<string[]> {
  const found = new Set(await page.locator("main nav a[href]").evaluateAll((as) => as.map((a) => a.getAttribute("href")!)));
  for (const picker of await page.locator('main nav button[aria-haspopup="dialog"]').all()) {
    if (!(await picker.isVisible())) continue;
    await picker.click();
    const sheet = page.locator("main nav dialog[open]");
    await expect(sheet).toBeVisible();
    for (const href of await sheet.locator("a[href]").evaluateAll((as) => as.map((a) => a.getAttribute("href")!))) found.add(href);
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
  }
  return [...found];
}

/** Visits each of `seeds`, and every address their tabs lead to that starts with one of `follow`. */
async function crawl(page: Page, who: string, seeds: string[], follow: string[], wide: string[], seen: string[]) {
  const done = new Set<string>();
  const queue = [...seeds];
  while (queue.length) {
    const url = queue.shift()!;
    if (done.has(url)) continue;
    done.add(url);
    seen.push(`${who} ${screen(url)}`);
    for (const l of await visit(page, who, url, wide)) if (!done.has(l) && !l.includes("#") && follow.some((f) => l.startsWith(f))) queue.push(l);
  }
}

test("no screen is wider than a phone", async ({ browser }) => {
  test.skip(test.info().project.name !== "phone", "phone only");
  // Some 170 screens, about five minutes on its own and more beside the rest of the suite.
  test.setTimeout(5 * 60_000);
  test.slow();
  const wide: string[] = [];
  const seen: string[] = [];

  const lead = await person(browser, "LayoutLead", { viewport });
  makeCustodian(lead.email);
  await lead.page.reload();
  const narrator = await person(browser, "LayoutNarrator", { viewport });
  const player = await person(browser, "LayoutPlayer", { viewport });
  const l = lead.page;
  const p = player.page;

  // A troupe with all its optional features on, so all its tabs show, and a long name, as a
  // select of troupes is as wide as its longest.
  const { id: troupeId } = await send(l, "POST", "/api/troupes", { name: `Layout Court of the Drowned Crown ${run}`, lead_handle: lead.handle });
  const base = `/troupes/${troupeId}`;
  await backstoryOptional(l, troupeId);
  await send(l, "PATCH", `/api${base}`, { description: "A Camarilla chronicle in a rain-soaked port city, where the old Prince's grip is slipping and every clan is counting favours." });
  await send(l, "PUT", `/api${base}/profile`, {
    schedule: "Second Saturday of the month, 7 pm to midnight",
    // Long enough to wrap on the troupe directory's row (#1192).
    content_notes: "Violence, body horror, and the slow loss of humanity; players set their own lines and veils with staff before play.",
    min_age: 18,
    links: {},
    setting: { chronicle: "The Drowned Crown", city: "Port Halden", era: "Modern nights" },
    venue: { name: "The Lantern Rooms", region: "Port Halden", address: "", access: "Step-free access" },
    new_players: "welcoming",
  });
  await send(l, "PUT", `/api${base}/staff`, { handle: narrator.handle, role: "narrator" });
  await send(l, "PUT", `/api${base}/boon-ledger`, { on: true });
  await send(l, "PUT", `/api${base}/blood-bonds`, { setting: "staff" });
  await send(l, "PUT", `/api${base}/player-nominations`, { on: true });
  await send(l, "PUT", `/api${base}/remembrances`, { on: true });
  await send(l, "PATCH", `/api${base}`, { court_history_players: true, chronicle_players: true });
  await send(l, "PUT", `/api${base}/quest-settings`, { enabled: true, requests_per_cycle: 1 });
  await send(l, "PUT", `/api${base}/golconda`, { on: true });
  await send(l, "PUT", `/api${base}/item-expiry`, { on: true });

  // A player with a character in the troupe, one asking to join it, and one in creation.
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]] as [string, number][], disciplines: [["Auspex", 2], ["Celerity", 1], ["Presence", 1]] as [string, number][] };
  const pc = await builtVampire(p, "Celestine Marrow", "Toreador", build);
  const asked = await send(p, "POST", `/api/characters/${pc}/home-troupe`, { troupe_id: troupeId });
  await send(l, "POST", `/api/approvals/${asked.id}/approve`, {});
  // A boon whose debtor is 600 characters of story, not a name (#990), owed to the player's character, who sees it.
  const story = "The debt was written in silver on the night the river froze, and sealed. ".repeat(9).slice(0, 600).trim();
  await send(l, "POST", `/api${base}/boons`, { boons: [{ debtor: { name: story }, creditor: { character_id: pc }, kind: "major", made_on: "2026-10-03", reason: "Passage" }], note: "" });
  await send(l, "PUT", `/api${base}/boon-players`, { see: "owed", settle: false });
  const pc2 = await builtVampire(p, "Ezra Vale", "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] });
  await send(p, "POST", `/api/characters/${pc2}/home-troupe`, { troupe_id: troupeId });
  const making = await creatingVampire(p, "Wren Halloway", "Brujah", []);

  // The court: two NPCs with titles.
  const npcs: string[] = [];
  for (const [name, clan, title] of [["Aurelia Vance", "Ventrue", "Prince"], ["Dane Kessler", "Brujah", "Sheriff"]] as const) {
    const npc = await send(l, "POST", `/api${base}/npcs`, { name, wizard: false });
    npcs.push(npc.id);
    await send(l, "PUT", `/api/characters/${npc.id}/npc/ratings`, { category: "sect", name: "Camarilla", rating: null, detail: "" });
    await send(l, "PUT", `/api/characters/${npc.id}/npc/ratings`, { category: "clan", name: clan, rating: null, detail: "" });
    await send(l, "PUT", `/api${base}/characters/${npc.id}/titles`, { titles: [title] });
  }

  // A game on now, a downtime cycle open with an action in, and a scene.
  const start = new Date(Date.now() - 30 * 60_000);
  start.setMinutes(0, 0, 0);
  const game = await send(l, "POST", `/api${base}/games`, { starts_at: start.toISOString(), ends_at: new Date(start.getTime() + 5 * 3600_000).toISOString() });
  const now = Date.now();
  const cycle = await send(l, "POST", `/api${base}/cycles`, { name: "Harvest Moon", closes_at: new Date(now + 7 * 86_400_000).toISOString(), grace_ends_at: new Date(now + 9 * 86_400_000).toISOString(), completion_xp: 2 });
  await send(l, "POST", `/api/cycles/${cycle.id}/open`);
  const form = await send(p, "GET", `/api/characters/${pc}/downtime`);
  const question = (form.questions as { id: string; prompt: string }[]).find((q) => q.prompt === "Downtime action")!;
  await send(p, "PUT", `/api/characters/${pc}/downtime/answers`, { answers: [{ question_id: question.id, slot: 1, body: "Host a salon for the Harpies and listen for talk of the Prince's health." }] });
  await send(p, "POST", `/api/characters/${pc}/downtime/submit`);
  const scene = await send(l, "POST", `/api${base}/scenes`, { name: "Elysium" });

  // A blog article with a long title and every tag, which the lead, the custodian too, publishes (#1158).
  const tagIds = ((await send(l, "GET", "/api/blog/tags")) as { id: string }[]).map((t) => t.id);
  const article = await send(l, "POST", "/api/blog/articles", { title: `Keeping a long-running chronicle of court intrigue fresh ${run}`, summary: story.slice(0, 300), body: `## Why\n\n${story}`, troupe_id: troupeId });
  await send(l, "PUT", `/api/blog/articles/${article.id}/tags`, { tag_ids: tagIds });
  await send(l, "POST", `/api/blog/articles/${article.id}/submit`);
  await send(l, "POST", `/api/blog/articles/${article.id}/publish`);
  await send(l, "PUT", `/api/blog/articles/${article.id}/featured`, { featured: true });

  // Signed out.
  const anon = await (await browser.newContext({ viewport })).newPage();
  // The troupe shows its profile to anyone, so the landing page (#1164) and the directory have
  // a troupe to list with a long name, and its public profile is all there.
  await send(l, "PUT", `/api${base}/profile/public`, { public: true });
  // The troupe directory (#1192), and a search that is sure to find it among other runs' troupes.
  const directory = `/find-a-troupe?name=${encodeURIComponent(`Drowned Crown ${run}`)}&new=1`;
  for (const url of ["/", "/find-a-troupe", directory, "/sign-in", "/sign-up", "/forgot-password", "/about", "/help", "/help/getting-started", `/t/${troupeId}`, "/blog", `/blog/${article.slug}`, "/blog/tags/storytelling"]) {
    seen.push(`anon ${screen(url)}`);
    await visit(anon, "anon", url, wide);
  }

  // The player: a character in creation opens on Create (#915).
  const mine = [`/characters/${pc}`, `/characters/${making}`, base, "/account", "/help"];
  await crawl(p, "player", ["/characters", ...mine, "/troupes", "/rules", "/check-in", "/characters/import", `/characters/${pc2}`], mine, wide, seen);
  for (const url of [`/play/characters/${pc}`, `/play/characters/${pc}?tab=boons`, `/play/characters/${pc}/ledger`, `/print/characters/${pc}`]) {
    seen.push(`player ${screen(url)}`);
    await visit(p, "player", url, wide);
  }

  // The narrator.
  await crawl(narrator.page, "narrator", [base], [base], wide, seen);

  // The storyteller, who is the custodian too.
  const staffSeeds = [base, "/custodian", `/characters/${pc}`, `${base}/games/${game.id}`, `${base}/downtimes/${cycle.id}`, `${base}/npcs/${npcs[0]}`, `/characters/${npcs[0]}`];
  await crawl(l, "staff", staffSeeds, [base, "/custodian", `/characters/${pc}`, `/characters/${npcs[0]}`], wide, seen);
  for (const url of [`/play/troupes/${troupeId}/scenes`, `/play/troupes/${troupeId}/scenes/${scene.id}`, "/charts"]) {
    seen.push(`staff ${screen(url)}`);
    await visit(l, "staff", url, wide);
  }

  // The walk reached the troupe's tabs at the back of its picker, not only the first few.
  expect(seen).toContain(`staff ${screen(`${base}/export-and-import`)}`);
  expect(seen).toContain(`player ${screen(`/characters/${pc}/results`)}`);
  // The boons screen's own tabs (#982): To review, Boonbreakers and Audits each at an address of its own.
  for (const part of ["review", "boonbreakers", "audits"]) expect(seen).toContain(`staff ${screen(`${base}/boons/${part}`)}`);
  expect(wide, `Wider than a ${viewport.width}px phone, of ${seen.length} screens`).toEqual([]);
});

/**
 * The desktop top bar is one line and fits the window at its narrowest, 1024px, with Large
 * text too (#1190), and at 1280px: for the widest bar there is, a custodian with a long name
 * (#746). Large text cuts the name shorter, and at 1024px drops "(custodian)" so the name keeps
 * at least ten letters (#1198); the account link still has both whole.
 */
test("the desktop top bar fits a 1024px window, with Large text too", async ({ browser }) => {
  test.skip(test.info().project.name !== "desktop", "desktop only");
  const { page, email } = await person(browser, "LayoutBarLarge-custodian-with-a-long-name", { viewport: { width: 1024, height: 800 } });
  const name = "LayoutBarLarge-custodian-with-a-long-name";
  makeCustodian(email);
  const wide: string[] = [];
  const labels: string[] = [];
  const fontSize = () => page.evaluate(() => getComputedStyle(document.documentElement).fontSize);
  const account = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: new RegExp(`^Your account: ${name} \\(custodian\\)$`) });
  for (const [size, px] of [["normal", "16px"], ["large", "18.4px"]] as const) {
    await send(page, "PATCH", "/api/preferences", { text_size: size });
    for (const width of [1024, 1280]) {
      await page.setViewportSize({ width, height: 800 });
      for (const url of ["/characters", "/custodian", "/account"]) {
        await page.goto(url);
        await expect(account).toBeVisible();
        await expect.poll(fontSize).toBe(px);
        await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
        const at = `${size} text, ${width}px, ${url}`;
        const over = await overflow(page);
        if (over) wide.push(`${at}: ${over}`);
        const height = (await page.getByRole("banner").boundingBox())!.height;
        if (height > 80) wide.push(`${at}: the top bar is ${Math.round(height)}px tall, more than one line`);
        // "(custodian)" shows where there's room for it; where not, it wraps out of sight.
        const bar = await account.evaluate((a, name) => {
          const spans = [...a.querySelectorAll("span")];
          const label = spans.find((s) => s.textContent === " (custodian)")!;
          const shown = label.getBoundingClientRect().top < label.parentElement!.getBoundingClientRect().bottom;
          const text = spans.find((s) => s.textContent === name && s.childElementCount === 0)!;
          const ruler = document.createElement("canvas").getContext("2d")!;
          ruler.font = getComputedStyle(text).font;
          return { shown, width: text.clientWidth, tenLetters: ruler.measureText(`${name.slice(0, 10)}…`).width };
        }, name);
        // Shown at Normal text; hidden at Large text and 1024px. Large at 1280px is up to the room.
        const wanted = size === "normal" ? true : width === 1024 ? false : bar.shown;
        if (bar.shown !== wanted) labels.push(`${at}: "(custodian)" is ${bar.shown ? "shown" : "hidden"}`);
        if (bar.width < bar.tenLetters) labels.push(`${at}: the name is ${bar.width}px, less than ten letters (${Math.round(bar.tenLetters)}px)`);
      }
    }
  }
  expect(wide, "The top bar is wider than the window or more than one line").toEqual([]);
  expect(labels, "The name or its label in the top bar").toEqual([]);
  // Cut short, the name and its label are whole in the link's name and its tooltip.
  await expect(account).toHaveAttribute("title", `${name} (custodian)`);
  await page.screenshot(shots("top-bar-large-text"));
});
