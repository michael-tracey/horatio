import { execFileSync } from "node:child_process";
import { expect, test, type Browser, type BrowserContextOptions, type Locator, type Page } from "@playwright/test";

/**
 * What the e2e specs share: signing people up, and building characters through the
 * API. Every test in a worker shares one `run`, whatever its file, so a person or
 * troupe name used by two tests clashes (src/e2eNames.test.ts guards it).
 */

export const run = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
export const PASSWORD = "a long enough password";
export const shots = (name: string) => ({ path: `test-results/screens/${test.info().project.name}-${name}.png`, fullPage: true });

/**
 * The Play View's Undo, in its header on every tab, once it says it takes back
 * `tap` (the log's line for it, or a pattern for the start of it).
 */
export async function undoInHeader(page: Page, tap: string | RegExp) {
  const undo = page.getByRole("banner").getByRole("button", { name: "Undo", exact: true });
  await expect(undo).toHaveAccessibleDescription(typeof tap === "string" ? `Undo ${tap}` : new RegExp(`^Undo ${tap.source}`));
  return undo;
}

/** Which group each of a PC's tabs is in on a phone (CharacterPage). */
const CHARACTER_GROUPS: Record<string, string> = {
  Sheet: "Sheet",
  "Status & Titles": "Sheet",
  Equipment: "Sheet",
  Experience: "Sheet",
  "Shared backgrounds": "Sheet",
  Downtime: "Between games",
  Results: "Between games",
  Quests: "Between games",
  Influence: "Between games",
  Troupes: "About",
  Backstory: "About",
  Log: "About",
};

/** A tab's name, with or without a count after it ("Results 2 new"). */
const tabName = (name: string) => new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}( \\d+\\+? \\w+)?$`);

/**
 * Opens a tab of a PC's page: in its one row on a wide screen; on a phone,
 * through its group, unless the group is open or is that tab alone.
 */
export async function characterTab(page: Page, name: string) {
  const main = page.locator("main");
  if ((page.viewportSize()?.width ?? 1280) >= 640) return main.getByRole("link", { name: tabName(name) }).click();
  const sections = main.getByRole("navigation", { name: "Tab groups" });
  await sections.waitFor();
  const alone = sections.getByRole("link", { name: tabName(name) });
  if (await alone.count()) return alone.click();
  const group = CHARACTER_GROUPS[name] ?? name;
  const tabs = main.getByRole("navigation", { name: group, exact: true });
  if (!(await tabs.isVisible())) await sections.getByRole("link", { name: tabName(group) }).click();
  await tabs.getByRole("link", { name: tabName(name) }).click();
}

export async function person(browser: Browser, name: string, options: BrowserContextOptions = {}): Promise<{ page: Page; email: string; handle: string }> {
  const page = await (await browser.newContext(options)).newPage();
  const email = `${name}-${run}@example.com`;
  // Unique to the run, and within a handle's 30 characters.
  const handle = `${name.slice(0, 14)}_${run.slice(-10)}`;
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill(name);
  await page.getByLabel("Handle").fill(handle);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your characters" })).toBeVisible();
  return { page, email, handle };
}

// Playwright leaves contexts made from `browser` open after the test. Each page in
// them goes on polling the API, so by the end of a worker's run hundreds of them
// load the one server the later tests wait on. Screenshots and traces of a failure
// are taken before this, and as each context closes. A hook written here would
// only reach the first spec a worker loads, so each spec calls this at its top.
export function closeContextsAfterEach() {
  test.afterEach(async ({ browser }) => {
    await Promise.all(browser.contexts().map((context) => context.close()));
  });
}

export function makeCustodian(email: string) {
  execFileSync("uv", ["run", "python", "-m", "horatio.custodian", email], { cwd: "../backend", stdio: "ignore" });
}

/** Lets a troupe accept characters without an approved backstory, as a troupe needs
 * one by default: for tests about something else. `p` is the custodian or one of
 * the troupe's storytellers; `troupe` is its id or its name. */
export async function backstoryOptional(p: Page, troupe: string) {
  let id = troupe;
  if (!/^[0-9a-f-]{36}$/.test(troupe)) {
    const troupes: { id: string; name: string }[] = await (await p.request.get("/api/troupes")).json();
    id = troupes.find((t) => t.name === troupe)!.id;
  }
  const response = await p.request.put(`/api/troupes/${id}/backstory-settings`, { headers: { "X-Horatio": "1" }, data: { mode: "free", required: false } });
  expect(response.status(), await response.text()).toBeLessThan(300);
}

/** A vampire in character creation built through the API: its clan, the in-clan
 * disciplines it chooses, and the creation picks of `build`. */
export async function creatingVampire(p: Page, name: string, clan: string, inClan: string[], build: Record<string, [string, number][]> = {}) {
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: clan, rating: null });
  for (const discipline of inClan) await send("PUT", `/api/characters/${id}/traits`, { category: "extra_in_clan_disciplines", name: discipline, rating: 1 });
  for (const [category, picks] of Object.entries(build))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([trait, rating]) => ({ name: trait, rating })) });
  return id as string;
}

/** The creation wizard's slots for the picks at one rating of a category ("Skills", "Physical Focus"). */
export function slotsAt(p: Page, section: string, rating: number) {
  return p.getByRole("group", { name: `${section} at ${rating}`, exact: true });
}

/** What the slots at one rating hold, for `expect.poll`: each slot's trait, or "" while empty. */
export function pickedAt(p: Page, section: string, rating: number) {
  return () =>
    slotsAt(p, section, rating)
      .getByRole("combobox")
      .evaluateAll((boxes) => boxes.map((box) => (box as HTMLInputElement).value));
}

/** Opens a slot's list of traits (the `nth` at that rating), returning the list. */
export async function openSlot(p: Page, section: string, rating: number, nth = 0) {
  const slot = slotsAt(p, section, rating).getByRole("combobox").nth(nth);
  await slot.scrollIntoViewIfNeeded();
  await slot.click();
  const list = p.locator(`[id="${await slot.getAttribute("aria-controls")}"]`);
  await expect(list).toBeVisible();
  return list;
}

/** One trait in an open slot's list, with why it can't be chosen (and links to where) beside it. */
export function choiceIn(list: Locator, trait: string) {
  return list.locator(`[data-choice="${trait}"]`);
}

/** Each slot's trait ("" while empty) and the id of its list, read in one go. */
function slotStates(slots: Locator) {
  return slots.evaluateAll((boxes) => boxes.map((box) => ({ value: (box as HTMLInputElement).value, list: box.getAttribute("aria-controls") ?? "" })));
}

/** Chooses `trait` in a slot at `rating`: the first empty one, or the `nth`, swapping or
 * replacing what is there. Typing narrows the list, as a player would on a long one. */
export async function choosePick(p: Page, section: string, rating: number, trait: string, nth?: number) {
  const slots = slotsAt(p, section, rating).getByRole("combobox");
  await expect(slots.first()).toBeVisible();
  const states = await slotStates(slots);
  const at = nth ?? states.findIndex((s) => !s.value);
  if (at === -1) throw new Error(`No empty slot at ${rating} in ${section}`);
  const slot = slots.nth(at);
  await slot.fill(trait);
  await p.locator(`[id="${states[at]!.list}"]`).getByRole("option", { name: trait, exact: true }).click();
  await expect(slot).toHaveValue(trait);
}

/** Chooses each trait at its rating, as `choosePick` does. */
export async function choosePicks(p: Page, section: string, picks: [string, number][]) {
  for (const [trait, rating] of picks) await choosePick(p, section, rating, trait);
}

/** Chooses each "Trait N" (such as "Brawl 4") in an empty slot at N, in whichever of the
 * step's categories offers it: a quick way through a whole step (Focuses has three). */
export async function chooseDots(p: Page, ...dots: string[]) {
  for (const dot of dots) {
    const [, trait, rating] = dot.match(/^(.*) (\d+)$/)!;
    const groups = p.getByRole("group", { name: new RegExp(` at ${rating}$`) });
    await expect(groups.first()).toBeVisible();
    let chosen = false;
    for (const group of await groups.all()) {
      const slots = group.getByRole("combobox");
      const states = await slotStates(slots);
      const at = states.findIndex((s) => !s.value);
      if (at === -1) continue;
      const slot = slots.nth(at);
      await slot.fill(trait!);
      const option = p.locator(`[id="${states[at]!.list}"]`).getByRole("option", { name: trait, exact: true });
      // Another category's slots (Focuses: Physical, Social, Mental) may not offer it.
      if (!(await option.count())) {
        await p.keyboard.press("Escape");
        continue;
      }
      await option.click();
      await expect(slot).toHaveValue(trait!);
      chosen = true;
      break;
    }
    if (!chosen) throw new Error(`No empty slot offers ${dot}`);
  }
}

/** Taps a button after bringing it to the middle of the screen, clear of the sticky counters on a phone. */
export async function tapMid(p: Page, name: string) {
  const button = p.getByRole("button", { name });
  await button.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await button.click();
}

export const CAITIFF_THREE = ["Auspex", "Celerity", "Potence"];

/** A new scene in the troupe, made through the API, opened on the page. */
export async function openScene(page: Page, troupeId: string, name: string): Promise<string> {
  const made = await page.request.post(`/api/troupes/${troupeId}/scenes`, { headers: { "X-Horatio": "1" }, data: { name } });
  expect(made.status(), await made.text()).toBe(201);
  const sceneId: string = (await made.json()).id;
  await page.goto(`/play/troupes/${troupeId}/scenes/${sceneId}`);
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  return sceneId;
}

/** A finished vampire built through the API, with self-entered XP to spend. */
export async function builtVampire(p: Page, name: string, clan: string, build: Record<string, [string, number][]>, raises: [string, string, number][] = []) {
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: clan, rating: null });
  for (const [category, picks] of Object.entries(build))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});
  await send("POST", `/api/characters/${id}/xp/self-entered`, { amount: 200, reason: "Played elsewhere" });
  for (const [category, trait, rating] of raises) await send("PUT", `/api/characters/${id}/traits`, { category, name: trait, rating });
  return id as string;
}

export const ATTRIBUTES_AND_FOCUSES: Record<string, [string, number][]> = {
  attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
  focus_physicals: [["Strength", 1]],
  focus_mentals: [["Wits", 1]],
  focus_socials: [["Charisma", 1]],
  skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
};
