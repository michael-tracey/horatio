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

/**
 * Switches one of a troupe's optional features on or off, by its row in the Features list
 * of Troupe settings (#783), the one place each is switched (#784). Waits for the toast.
 */
export async function switchFeature(page: Page, troupeId: string, name: string, on: boolean) {
  await settingsPart(page, troupeId);
  const toggle = page.getByRole("list", { name: "Features" }).getByRole("switch", { name, exact: true });
  await expect(toggle).toHaveAttribute("aria-checked", String(!on));
  await toggle.click();
  await expect(page.getByText(`${name}: switched ${on ? "on" : "off"}.`)).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-checked", String(on));
}

/**
 * A troupe tab's own settings (#909): the dialog its Settings button opens, named
 * "<tab> settings" ("Boons settings", "Approvals settings"). An address ending `#settings`
 * or `#settings-<part>` opens it already, so the button is pressed only without one.
 */
export async function tabSettings(page: Page, tab: string): Promise<Locator> {
  const dialog = page.getByRole("dialog", { name: `${tab} settings` });
  if (!/#settings(-[a-z-]+)?$/.test(page.url())) await page.locator("main").getByRole("button", { name: "Settings", exact: true }).click();
  await expect(dialog).toBeVisible();
  return dialog;
}

/** Closes a tab's settings dialog (`tabSettings`), back to the tab: its ×, or Close across its foot on a phone. */
export async function closeTabSettings(dialog: Locator) {
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
}

/**
 * The site's main navigation in the top bar (#746): the bar itself on a wide screen;
 * below 1024px, behind the Menu button, which this opens if it isn't open already.
 * Characters, Troupes, Rulebook, Help, Custodian, the account link and Sign
 * out are all in it.
 */
export async function topBar(page: Page): Promise<Locator> {
  const nav = page.getByRole("navigation", { name: "Main" });
  if ((page.viewportSize()?.width ?? 1280) >= 1024) return nav;
  const menu = page.getByRole("button", { name: "Menu", exact: true });
  if ((await menu.getAttribute("aria-expanded")) !== "true") await menu.click();
  return nav;
}

/**
 * Opens the custodian's New troupe form, under Custodian › Troupe management
 * (#759), from wherever the page is.
 */
export async function openNewTroupe(page: Page): Promise<void> {
  await page.goto("/custodian/troupe-management");
  await expect(page.getByRole("heading", { name: "New troupe" })).toBeVisible();
}

/** A tab's name, with or without a count after it ("Results 2 new", "Being built 1 being built"). */
const tabName = (name: string) => new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}( \\d+\\+? [\\w ]+)?$`);

/** Below `sm`, where a page's tabs are one section picker (#904). */
export const isPhone = (page: Page) => (page.viewportSize()?.width ?? 1280) < 640;

/**
 * On a phone, opens the section picker named `nav` ("Troupe sections",
 * "Character tabs") and gives its sheet, where every tab is; Escape shuts it.
 */
export async function openSections(page: Page, nav = "Troupe sections"): Promise<Locator> {
  await page.locator("main").getByRole("navigation", { name: nav, exact: true }).getByRole("button").click();
  const sheet = page.getByRole("dialog", { name: nav });
  await expect(sheet).toBeVisible();
  return sheet;
}

/** Shuts the section picker's sheet on a phone; nothing on a wide screen. */
export async function shutSections(page: Page, nav = "Troupe sections") {
  if (!isPhone(page)) return;
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: nav })).toBeHidden();
}

/**
 * A group's tabs: its own row on a wide screen, while the group is open; on a
 * phone, its list in the section picker's sheet, which this opens (`shutSections` shuts it).
 */
export async function groupTabs(page: Page, group: string, nav = "Troupe sections"): Promise<Locator> {
  if (!isPhone(page)) return page.locator("main").getByRole("navigation", { name: group, exact: true });
  return (await openSections(page, nav)).getByRole("list", { name: group, exact: true });
}

/** On a phone, opens a tab through the section picker named `nav`. */
async function pickSection(page: Page, nav: string, name: string) {
  const sheet = await openSections(page, nav);
  await sheet.getByRole("link", { name: tabName(name) }).click();
  await expect(sheet).toBeHidden();
}

/**
 * Opens a tab of a PC's page: in its one row on a wide screen; on a phone,
 * through the section picker.
 */
export async function characterTab(page: Page, name: string) {
  if (isPhone(page)) return pickSection(page, "Character tabs", name);
  return page.locator("main").getByRole("link", { name: tabName(name) }).click();
}

/**
 * That `tab` of `group` is the one open: marked in the group's own row on a wide
 * screen; on a phone, named on the section picker ("Court, Bonds").
 */
export async function expectTabOpen(page: Page, group: string, tab: string, nav = "Troupe sections") {
  const main = page.locator("main");
  if (isPhone(page)) {
    const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const named = group === tab ? escape(tab) : `${escape(group)}\\W+${escape(tab)}`;
    return expect(main.getByRole("navigation", { name: nav, exact: true }).getByRole("button")).toHaveAccessibleName(new RegExp(`^${named}\\b`));
  }
  await expect(main.getByRole("navigation", { name: group, exact: true }).getByRole("link", { name: tabName(tab) })).toHaveAttribute("aria-current", "page");
}

/**
 * That a tab in sight shows a count, such as "1 waiting", or none (`null`): in the
 * open group's row on a wide screen; on a phone, in the section picker's sheet, shut again after.
 */
export async function expectTabCount(page: Page, tab: string, count: string | null, nav = "Troupe sections") {
  const shown = (within: Locator) =>
    count === null ? within.getByRole("link", { name: tab, exact: true }) : within.getByRole("link", { name: tabName(tab) }).getByLabel(count);
  if (!isPhone(page)) return expect(shown(page.locator("main"))).toBeVisible();
  const sheet = await openSections(page, nav);
  await expect(shown(sheet)).toBeVisible();
  await shutSections(page, nav);
}

/** The group(s) each of a troupe's tabs is in (troupeTabs.ts): House rules is under Customise for those who change it. */
const TROUPE_GROUPS: Record<string, string[]> = {
  Overview: ["Troupe"],
  "The setting": ["Troupe"],
  "Story bible": ["Troupe"],
  "Who's Who": ["Troupe"],
  News: ["Troupe"],
  Announcements: ["Troupe"],
  Nominations: ["Troupe"],
  Remembrances: ["Troupe"],
  "House rules": ["Customise", "Troupe"],
  Staff: ["Troupe"],
  Log: ["Troupe"],
  Approvals: ["Characters"],
  "Being built": ["Characters"],
  Roster: ["Characters"],
  Players: ["Characters"],
  "Lines and veils": ["Characters"],
  "At game": ["Games"],
  Scenes: ["Games"],
  "Award XP": ["Games"],
  Titles: ["Court"],
  "Court over time": ["Court"],
  Chronicle: ["Court"],
  Boons: ["Court"],
  Bonds: ["Court"],
  "Web of obligation": ["Court"],
  Cycles: ["Downtimes"],
  "My work": ["Downtimes"],
  "Fill tables": ["Downtimes"],
  "Influence log": ["Downtimes"],
  Quests: ["Downtimes"],
  Locations: ["World"],
  Equipment: ["World"],
  "Shared backgrounds": ["World"],
  Setup: ["Customise"],
  "Troupe settings": ["Customise"],
  Specialisations: ["Customise"],
  "News agencies": ["Customise"],
  Connectors: ["Customise"],
  "Export and import": ["Customise"],
};

/**
 * Opens a tab of a troupe's page from wherever on it: on a wide screen through
 * its group in the row, unless that group is open; on a phone through the
 * section picker (#904).
 */
export async function troupeTab(page: Page, name: string) {
  if (isPhone(page)) return pickSection(page, "Troupe sections", name);
  const main = page.locator("main");
  const sections = main.getByRole("navigation", { name: "Troupe sections" });
  await sections.waitFor();
  const groups = TROUPE_GROUPS[name];
  if (!groups) throw new Error(`No troupe tab named ${name}`);
  let group = groups[0]!;
  for (const g of groups) {
    if (await sections.getByRole("link", { name: tabName(g) }).count()) {
      group = g;
      break;
    }
  }
  const tab = main.getByRole("navigation", { name: group, exact: true }).getByRole("link", { name: tabName(name) });
  if (await tab.isVisible()) return tab.click();
  const groupLink = sections.getByRole("link", { name: tabName(group) });
  await groupLink.click();
  await expect(groupLink).toHaveAttribute("aria-current", "true");
  // A group of one is its tab; a group of more opens its first, or the one it names.
  if (await tab.count()) await tab.click();
}

/** Below `lg`, where a page's parts are one part picker's button (#906). */
export const isNarrow = (page: Page) => (page.viewportSize()?.width ?? 1280) < 1024;

/**
 * Opens a part of a page with a part picker (#906), such as House rules › Costs:
 * in its list down the side on a wide screen; below `lg`, through its button and
 * sheet. `nav` names the picker: "House rules", "Specialisations".
 */
export async function pagePart(page: Page, name: string, nav = "House rules") {
  const picker = page.locator("main").getByRole("navigation", { name: nav, exact: true });
  if (!isNarrow(page)) return picker.getByRole("link", { name, exact: true }).click();
  await picker.getByRole("button").click();
  const sheet = page.getByRole("dialog", { name: nav });
  await sheet.getByRole("link", { name, exact: true }).click();
  await expect(sheet).toBeHidden();
}

/** That `name` is the open part of the part picker `nav`: marked in its list on a wide screen, named on its button below `lg`. */
export async function expectPartOpen(page: Page, name: string, nav = "House rules") {
  const picker = page.locator("main").getByRole("navigation", { name: nav, exact: true });
  if (!isNarrow(page)) return expect(picker.getByRole("link", { name, exact: true })).toHaveAttribute("aria-current", "page");
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // After its group's name, if it has one: "Backgrounds, Influence: Elite".
  await expect(picker.getByRole("button")).toHaveAccessibleName(new RegExp(`(^|\\W)${escaped}$`));
}

/** The parts of Troupe settings (#908), by their address under `settings/`; the Features list has none. */
const SETTINGS_PARTS = {
  features: "Features",
  setting: "The setting",
  joining: "Who may join",
  xp: "XP",
  status: "Status and titles",
  blood: "Blood, diablerie and feeding",
  names: "Names",
} as const;

/**
 * Goes to a part of a troupe's Troupe settings (#908) at its own address, `settings/xp` say,
 * or to the Features list it opens on, and waits until it is the open part.
 */
export async function settingsPart(page: Page, troupeId: string, part: keyof typeof SETTINGS_PARTS = "features") {
  await page.goto(`/troupes/${troupeId}/settings${part === "features" ? "" : `/${part}`}`);
  await expectPartOpen(page, SETTINGS_PARTS[part], "Troupe settings");
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
  // Wait on the sign-up itself, as the page moves on only once it answers: while the
  // other worker loads a heavy page, the one API server has taken over 5 s (#878).
  const [signedUp] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/api/auth/signup") && r.request().method() === "POST"),
    page.getByRole("button", { name: "Create account" }).click(),
  ]);
  expect(signedUp.status(), await signedUp.text()).toBe(201);
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

/** Below `lg` the creation steps are one line, "Step 3 of 8 · Focuses", that opens their list in a dialog (#916). */
const stepsInDialog = (p: Page) => (p.viewportSize()?.width ?? 1280) < 1024;

/**
 * Looks at the creation wizard's list of steps: down the side on a wide screen; on a
 * phone, in the dialog its step line opens, closed again after `look`.
 */
export async function inSteps(p: Page, look: (steps: Locator) => Promise<void>) {
  const nav = p.getByRole("navigation", { name: "Creation steps" });
  if (!stepsInDialog(p)) return look(nav);
  await nav.getByRole("button", { name: /^Step \d+ of \d+/ }).click();
  const dialog = nav.getByRole("dialog", { name: "Creation steps" });
  await look(dialog);
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
}

/** Goes to a creation step through the list of steps (on a phone, the list the step line opens). */
export async function goToStep(p: Page, name: RegExp) {
  const nav = p.getByRole("navigation", { name: "Creation steps" });
  if (stepsInDialog(p)) await nav.getByRole("button", { name: /^Step \d+ of \d+/ }).click();
  const list = stepsInDialog(p) ? nav.getByRole("dialog", { name: "Creation steps" }) : nav;
  await list.getByRole("link", { name }).click();
  await expect(nav.getByRole("dialog")).toBeHidden();
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

/** The detail under an open list (ChoiceBox): what the highlighted choice does. */
export function aboutChoice(p: Page) {
  return p.getByRole("region", { name: "About the highlighted choice" });
}

/**
 * Chooses `option` in a drop-down that explains its choices (ChoiceBox) named `label`,
 * such as Concept's "Clan" in the creation wizard. Typing narrows the list, as a player
 * would on a long one. The choice may still be refused once saved: the caller checks it.
 */
export async function chooseIn(p: Page, label: string, option: string) {
  const box = p.getByRole("combobox", { name: label, exact: true });
  await box.scrollIntoViewIfNeeded();
  await box.fill(option);
  const list = p.locator(`[id="${await box.getAttribute("aria-controls")}"]`);
  await list.getByRole("option", { name: option, exact: true }).click();
  await expect(list).toBeHidden();
}

/**
 * Opens the sheet's Add panel's list of a category ("Merits", "Elder Disciplines"),
 * returning it: a tap on its search box, which a choice made outside it (a chip, the
 * Show filter) has closed. Typing in the box opens it too.
 */
export async function addList(p: Page, category: string) {
  const box = p.getByRole("combobox", { name: `Search ${category}`, exact: true });
  await box.scrollIntoViewIfNeeded();
  await box.click();
  const list = p.locator(`[id="${await box.getAttribute("aria-controls")}"]`);
  await expect(list).toBeVisible();
  return list;
}

/** Each slot's trait ("" while empty) and the id of its list, read in one go. */
function slotStates(slots: Locator) {
  return slots.evaluateAll((boxes) => boxes.map((box) => ({ value: (box as HTMLInputElement).value, list: box.getAttribute("aria-controls") ?? "" })));
}

/** Chooses `trait` in a slot at `rating`: the first empty one, or the `nth`, swapping or
 * replacing what is there. A trait picked at another rating is offered as "Brawl (at 3)",
 * and moves. Typing narrows the list, as a player would on a long one. */
export async function choosePick(p: Page, section: string, rating: number, trait: string, nth?: number) {
  const slots = slotsAt(p, section, rating).getByRole("combobox");
  await expect(slots.first()).toBeVisible();
  const states = await slotStates(slots);
  const at = nth ?? states.findIndex((s) => !s.value);
  if (at === -1) throw new Error(`No empty slot at ${rating} in ${section}`);
  const slot = slots.nth(at);
  await slot.fill(trait);
  const escaped = trait.replace(/[.*+?^$()|[\]\\{}]/g, "\\$&");
  const name = new RegExp(`^${escaped}( \\(at \\d+\\))?$`);
  await p.locator(`[id="${states[at]!.list}"]`).getByRole("option", { name }).click();
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
