import { execFileSync } from "node:child_process";
import { expect, test, type Browser, type BrowserContextOptions, type Page } from "@playwright/test";

/**
 * What the e2e specs share: signing people up, and building characters through the
 * API. Every test in a worker shares one `run`, whatever its file, so a person or
 * troupe name used by two tests clashes (src/e2eNames.test.ts guards it).
 */

export const run = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
export const PASSWORD = "a long enough password";
export const shots = (name: string) => ({ path: `test-results/screens/${test.info().project.name}-${name}.png`, fullPage: true });

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
