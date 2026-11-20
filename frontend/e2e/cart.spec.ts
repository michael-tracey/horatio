import { expect, test } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, builtVampire, ATTRIBUTES_AND_FOCUSES, backstoryOptional, characterTab, tapMid, tabSettings, aboutChoice, addList } from "./support";

/** The XP cart: changes on the sheet wait in it until Spend XP makes them. */

closeContextsAfterEach();

test("Generation changes in the cart until a home troupe accepts the character, repricing earlier buys", async ({ browser }) => {
  const custodian = await person(browser, "gen-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "gen-lead");
  const player = await person(browser, "gen-player");
  const troupeName = `Court of the Unaccepted ${run}`;
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;

  // Ottoline, a Neonate (Generation 1), finishes creation and buys Brawl and Herd at a Neonate's prices: 5 and 3 XP.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Ottoline" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const build: Record<string, [string, number][]> = {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, picks] of Object.entries(build))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});
  await send("PUT", `/api/characters/${id}/traits`, { category: "skills", name: "Brawl", rating: 5 });
  await send("PUT", `/api/characters/${id}/traits`, { category: "backgrounds", name: "Herd", rating: 3 });
  await p.goto(`/characters/${id}`);
  const cart = p.getByRole("list", { name: "Changes in the cart" });

  // No troupe has accepted her yet, so Generation still goes up in the cart: 4 XP, and the earlier buys at Generation 2's prices.
  await p.getByRole("button", { name: "Raise Generation" }).click();
  const line = cart.getByRole("listitem").filter({ hasText: "Generation 1 → 2" });
  await expect(line).toContainText("Generation 1 → 2 · 12 XP");
  await expect(line).toContainText("Earlier buys repriced at the new Generation, 8 XP in all: Brawl 4 → 5 (5 XP), Herd 2 → 3 (3 XP).");
  await p.screenshot(shots("generation-repriced"));
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 12 XP.")).toBeVisible();
  await characterTab(p, "Experience");
  await expect(p.getByText("Generation 1 → 2: Brawl 4 → 5 repriced")).toBeVisible();
  await expect(p.getByText("Generation 1 → 2: Herd 2 → 3 repriced")).toBeVisible();

  // Down again refunds the dot and reprices back; the creation pick stays.
  await p.goto(`/characters/${id}`);
  await p.getByRole("button", { name: "Lower Generation" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Generation 2 → 1" })).toContainText("8 XP back in all");
  await expect(p.getByRole("button", { name: "Lower Generation" })).toBeDisabled();
  await p.getByRole("button", { name: "Clear" }).click();

  // The lead sees the Generation being accepted, and that accepting locks it.
  const asked = await send("POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  expect(asked.id).toBeTruthy();
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/approvals`);
  const card = l.locator("section").filter({ hasText: "Ottoline" });
  await expect(card).toContainText("Accepting at 9th generation (Generation background ●●).");
  await expect(card).toContainText("Accepting locks it");
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();

  // Once accepted, Generation is fixed.
  await p.reload();
  await p.getByRole("button", { name: "Raise Generation" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Generation 2 → 3" })).toContainText(
    "Generation can't change once a home troupe has accepted the character.",
  );
  await expect(p.getByRole("button", { name: "Spend XP" })).toBeDisabled();
});

test("a Ventrue takes Royalty from the sheet, places 4, 3 and 2 free dots, changes them until a troupe accepts the character, and not after", async ({ browser }) => {
  const custodian = await person(browser, "royal-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "royal-lead");
  const player = await person(browser, "royal-player");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of the Crown ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;

  // Cordelia, a finished Ventrue with two dots of Resources bought (3 XP at a Neonate's prices).
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Cordelia" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Ventrue", rating: null });
  const build: Record<string, [string, number][]> = {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Contacts", 2], ["Generation", 1]],
    disciplines: [["Dominate", 2], ["Fortitude", 1], ["Presence", 1]],
  };
  for (const [category, picks] of Object.entries(build))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});
  await send("PUT", `/api/characters/${id}/traits`, { category: "backgrounds", name: "Resources", rating: 2 });
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  const trait = (name: string) => p.locator(`li[data-trait="${name}"]`);
  const chosen = p.locator('[data-free-choices="Ventrue Royalty"]');

  // The Add panel asks for the choices as the merit goes in: 4 in Resources, 3 in Herd, 2 in Allies.
  // Until they have come, it shows it is loading them and can't be added without them (#576).
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await p.route("**/api/characters/*/free-choices?*", async (route) => {
    await held;
    await route.continue();
  });
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByRole("combobox", { name: "Search Merits", exact: true }).fill("Ventrue Royalty");
  await p.getByRole("option", { name: /^Ventrue Royalty/ }).click();
  await expect(p.getByRole("status", { name: "Loading its choices…" })).toBeVisible();
  await expect(p.getByRole("button", { name: "Add to cart" })).toBeDisabled();
  release();
  await expect(p.getByText("Choose your free backgrounds")).toBeVisible();
  await expect(p.getByRole("status", { name: "Loading its choices…" })).toHaveCount(0);
  await p.unrouteAll();
  await expect(p.getByText("Place 4, 3 and 2 dots, each in a different one.")).toBeVisible();
  await p.getByLabel("4 dots in").selectOption("Resources");
  await p.getByLabel("3 dots in").selectOption("Herd");
  await p.getByLabel("2 dots in").selectOption("Allies");
  // A background can be placed once: Resources is taken.
  await expect(p.getByLabel("3 dots in").getByRole("option", { name: "Resources" })).toBeDisabled();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Add Ventrue Royalty" })).toContainText("free: Resources 4, Herd 3, Allies 2");
  await p.getByRole("button", { name: "Spend XP" }).click();

  // The dots are free ones, and the 3 XP paid for Resources is back (2 XP for the merit, less 3).
  await expect(trait("Resources")).toContainText("+4 from Ventrue Royalty");
  await expect(trait("Herd")).toContainText("+3 from Ventrue Royalty");
  await expect(trait("Allies")).toContainText("+2 from Ventrue Royalty");
  await expect(chosen).toContainText("Resources 4");
  await expect(chosen).toContainText("Herd 3");
  await expect(chosen).toContainText("Allies 2");
  await expect(p.getByText("28", { exact: true })).toBeVisible();
  await p.screenshot(shots("royalty-placed"));

  // A dot bought above the free ones stays bought (#575): Herd's fourth costs 4 XP.
  await p.getByRole("button", { name: "Raise Herd" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Herd 3 → 4" })).toContainText("4 XP");
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(trait("Herd").getByLabel("4 dots", { exact: true })).toBeVisible();
  await expect(trait("Herd")).toContainText("+3 from Ventrue Royalty");
  await expect(p.getByText("24", { exact: true })).toBeVisible();

  // Until a troupe accepts her, the choices change freely: Haven in place of Resources.
  await p.getByRole("button", { name: "Edit the free traits for Ventrue Royalty" }).click();
  await p.getByLabel("4 dots in").selectOption("Haven");
  await p.getByRole("button", { name: "Save", exact: true }).click();
  await expect(trait("Haven")).toContainText("+4 from Ventrue Royalty");
  await expect(trait("Resources")).toHaveCount(0);
  await expect(chosen).toContainText("Haven 4");

  // The lead sees what she chose where the request is accepted.
  await send("POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/approvals`);
  const card = l.locator("section").filter({ hasText: "Cordelia" });
  await expect(card).toContainText("Free traits the player chose");
  await expect(card).toContainText("Ventrue Royalty: Haven 4, Herd 3, Allies 2");
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();

  // Once accepted, they are staff's to change.
  await p.reload();
  await expect(chosen).toContainText("Haven 4");
  await expect(chosen).toContainText("can't change once a home troupe has accepted");
  await expect(p.getByRole("button", { name: "Edit the free traits for Ventrue Royalty" })).toHaveCount(0);
  const refused = await p.request.fetch(`/api/characters/${id}/traits/choices`, {
    method: "PUT",
    headers,
    data: { category: "merits", name: "Ventrue Royalty", detail: "", picks: [] },
  });
  expect(refused.status()).toBe(409);
});

test("Walking Atrocity gives a bonus attribute dot for each dot of Morality below 5, and another when it drops", async ({ browser }) => {
  const custodian = await person(browser, "atrocity-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "atrocity-lead");
  const player = await person(browser, "atrocity-play");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Atrocities ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  await backstoryOptional(custodian.page, troupeId);

  // A Baali elder (Generation 3) on the Path of Evil Revelations, which starts at 4: one dot below 5.
  const p = player.page;
  const id = await builtVampire(
    p,
    "Zillah",
    "Baali",
    {
      ...ATTRIBUTES_AND_FOCUSES,
      backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]],
      disciplines: [["Daimoinon", 2], ["Obfuscate", 1], ["Presence", 1]],
      merits: [["Path of Evil Revelations", 3]],
    },
    [["disciplines", "Daimoinon", 5]],
  );
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  const trait = (name: string) => p.locator(`li[data-trait="${name}"]`);
  const placed = p.locator('[data-free-choices="Daimoinon: Walking Atrocity"]');
  const power = "Daimoinon: Walking Atrocity";

  // The Add panel asks where the dot goes as the power goes in.
  await part("Disciplines").getByRole("button", { name: "Add" }).click();
  await p.getByRole("navigation", { name: "Categories" }).getByRole("button", { name: /^Elder Disciplines/ }).click();
  await (await addList(p, "Elder Disciplines")).getByRole("option", { name: new RegExp(`^${power}`) }).click();
  await expect(p.getByText("Place your bonus attribute dots")).toBeVisible();
  await expect(p.getByText("Place 1 bonus dot, one for each dot of Morality below 5, up to 5 in one.")).toBeVisible();
  await p.getByLabel("Bonus dots in Physical").selectOption("1");
  // One dot only: none is left for Social.
  await expect(p.getByLabel("Bonus dots in Social").getByRole("option")).toHaveText(["0"]);
  await p.getByRole("button", { name: "Add to cart" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: `Add ${power}` })).toContainText("free: Physical 1");
  await p.getByRole("button", { name: "Spend XP" }).click();

  // The dot is free, and the attribute says where it came from.
  await expect(trait("Physical")).toContainText(`+1 from ${power}`);
  await expect(trait("Physical").getByLabel("8 dots", { exact: true })).toBeVisible();
  await expect(placed).toContainText("Physical 1");
  await p.screenshot(shots("walking-atrocity-placed"));

  // A home troupe accepts her; then a diablerie costs her a dot of her Path.
  const asked = await (await p.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } })).json();
  const accepted = await lead.page.request.post(`/api/approvals/${asked.id}/approve`, { headers, data: {} });
  expect(accepted.status(), await accepted.text()).toBe(200);
  const recorded = await lead.page.request.post(`/api/characters/${id}/diablerie`, {
    headers,
    data: { committed_on: "2026-10-31", victim: "A rival", humanity_lowered: 1 },
  });
  expect(recorded.status(), await recorded.text()).toBe(200);

  // Another dot to place, on the sheet. The one placed stays put.
  await p.reload();
  await expect(placed).toContainText("1 more to place");
  await p.getByRole("button", { name: `Choose the free traits for ${power}` }).click();
  await expect(placed.getByText("1 of 2 placed")).toBeVisible();
  await p.getByLabel("Bonus dots in Physical").selectOption("0");
  await p.getByLabel("Bonus dots in Mental").selectOption("2");
  await p.getByRole("button", { name: "Save", exact: true }).click();
  await expect(placed).toContainText("placed dots can't move once a home troupe has accepted");
  await p.getByLabel("Bonus dots in Mental").selectOption("0");
  await p.getByLabel("Bonus dots in Physical").selectOption("1");
  await p.getByLabel("Bonus dots in Social").selectOption("1");
  await p.getByRole("button", { name: "Save", exact: true }).click();
  await expect(trait("Social")).toContainText(`+1 from ${power}`);
  await expect(trait("Physical")).toContainText(`+1 from ${power}`);
  await expect(placed).not.toContainText("more to place");
});

test("once accepted, a merit or flaw is asked of the home troupe: one declined, a flaw bought off through a quest", async ({ browser }) => {
  test.slow();
  const custodian = await person(browser, "meritask-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "meritask-lead");
  const player = await person(browser, "meritask-play");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Asking ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;
  const l = lead.page;
  const settings = await l.request.put(`/api/troupes/${troupeId}/quest-settings`, { headers, data: { enabled: true, requests_per_cycle: 1 } });
  expect(settings.status(), await settings.text()).toBe(200);

  // Wilhelmina took Low Pain Threshold before the troupe accepted her.
  const p = player.page;
  const id = await builtVampire(p, "Wilhelmina", "Toreador", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]], disciplines: [["Auspex", 2], ["Celerity", 1], ["Presence", 1]] }, [
    ["flaws", "Low Pain Threshold", 3],
  ]);
  const asked = await p.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBe(201);
  const accepted = await l.request.post(`/api/approvals/${(await asked.json()).id}/approve`, { headers, data: {} });
  expect(accepted.status(), await accepted.text()).toBe(200);
  const awarded = await l.request.post(`/api/characters/${id}/xp`, { headers, data: { amount: 20, reason: "Last game" } });
  expect(awarded.status(), await awarded.text()).toBe(201);

  // Adding Rugged is asked of the troupe, its 3 XP held; buying off the flaw costs twice its points.
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  const trait = (name: string) => p.locator(`li[data-trait="${name}"]`);
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByRole("combobox", { name: "Search Merits", exact: true }).fill("Rugged");
  await p.getByRole("option", { name: /^Rugged/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await trait("Low Pain Threshold").getByRole("button", { name: "Remove Low Pain Threshold" }).click();
  const rugged = cart.getByRole("listitem").filter({ hasText: "Rugged" });
  // Each line is tried on the sheet as it is priced, which takes a while on a busy server.
  await expect(rugged).toContainText("Asked of the home troupe: 3 XP held until they decide.", { timeout: 15_000 });
  await expect(rugged).toContainText("Needs approval");
  await expect(cart.getByRole("listitem").filter({ hasText: "Low Pain Threshold" })).toContainText("buying it off costs 6 XP, twice what it gave");
  await p.screenshot(shots("merit-flaw-asked"));
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Some of it waits for the home troupe's approval.")).toBeVisible();
  // Nothing has changed on the sheet yet: both wait, marked.
  await expect(trait("Rugged")).toContainText("Awaiting approval");
  await expect(trait("Low Pain Threshold")).toContainText("Removal awaiting approval");
  await expect(part("Health Levels").getByRole("img", { name: "Injured: 2 boxes" })).toBeVisible();

  // The lead has both in the bell, and declines Rugged.
  await l.goto(`/troupes/${troupeId}`);
  await l.getByRole("button", { name: "Notifications, 2 waiting" }).click();
  await l.getByRole("button", { name: /Wilhelmina asks to add Rugged \(3 XP\)/ }).click();
  const ruggedCard = l.locator("section").filter({ hasText: "Add the merit Rugged" });
  await expect(ruggedCard).toContainText("for 3 XP");
  await ruggedCard.getByLabel("Note to the player").fill("Not this season.");
  await ruggedCard.getByRole("button", { name: "Decline" }).click();
  await expect(ruggedCard).toHaveCount(0);

  // The flaw is answered with a quest: the builder starts at Complex 3.
  const flawCard = l.locator("section").filter({ hasText: "Buy off the flaw Low Pain Threshold" });
  await expect(flawCard).toContainText("for 6 XP: twice what it gave");
  await flawCard.getByRole("button", { name: "Answer with a quest" }).click();
  await expect(l.getByLabel("Quest name")).toHaveValue("Buy off Low Pain Threshold");
  await expect(l.getByLabel("Category")).toHaveValue("complex");
  await expect(l.getByLabel("Difficulty")).toHaveValue("3");
  await l.screenshot(shots("merit-flaw-quest-builder"));
  await l.getByRole("button", { name: "Build the quest" }).click();
  await expect(l.getByText("It answers a request: Wilhelmina buys off Low Pain Threshold (6 XP held).")).toBeVisible();
  const questId = new URL(l.url()).pathname.split("/").at(-1)!;

  // The queue shows it waits on the quest, with no yes or no.
  await l.goto(`/troupes/${troupeId}/approvals`);
  await expect(flawCard).toContainText("Answered with the quest Buy off Low Pain Threshold (draft).");
  await expect(flawCard.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);

  // Its requirements sent and its three scenarios passed, the quest is completed.
  const post = async (url: string, data: object) => {
    const response = await l.request.post(url, { headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
  };
  await post(`/api/quests/${questId}/requirements`, { options: [{ kind: "text", text: "A sire's blessing" }] });
  await post(`/api/quests/${questId}/send`, {});
  await p.reload();
  await expect(p.getByText("answered with the quest Buy off Low Pain Threshold")).toBeVisible();
  for (const number of [1, 2, 3]) await post(`/api/quests/${questId}/scenarios/${number}/result`, { result: "passed" });

  // The flaw is gone and its lost health level back; Rugged's XP came back when declined.
  await p.reload();
  await expect(trait("Low Pain Threshold")).toHaveCount(0);
  await expect(trait("Rugged")).toHaveCount(0);
  await expect(part("Health Levels").getByRole("img", { name: "Injured: 3 boxes" })).toBeVisible();
  await characterTab(p, "Experience");
  await expect(p.getByText("Rugged 3 → 0 (declined)")).toBeVisible();
  await expect(p.getByText("Low Pain Threshold 3 → 0", { exact: true })).toBeVisible();
});

test("a finished Nosferatu asks staff for Bloodline: Creeps by exception, spends it, and the lead approves it", async ({ browser }) => {
  test.slow();
  const custodian = await person(browser, "creeps-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "creeps-lead");
  const player = await person(browser, "creeps-play");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of the Depths ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;

  // Silas, a Nosferatu, is built and accepted by the troupe.
  const p = player.page;
  const id = await builtVampire(p, "Silas", "Nosferatu", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]], disciplines: [["Animalism", 2], ["Obfuscate", 1], ["Potence", 1]] });
  const asked = await p.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBe(201);
  const accepted = await lead.page.request.post(`/api/approvals/${(await asked.json()).id}/approve`, { headers, data: {} });
  expect(accepted.status(), await accepted.text()).toBe(200);

  // A bloodline merit is for creation only: the cart refuses it, but offers to ask staff.
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByRole("combobox", { name: "Search Merits", exact: true }).fill("Bloodline: Creeps");
  await p.getByRole("option", { name: /^Bloodline: Creeps/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  const line = cart.getByRole("listitem").filter({ hasText: "Bloodline: Creeps" });
  await expect(line).toContainText("Bloodline: Creeps can only be chosen during character creation.", { timeout: 15_000 });
  await line.getByRole("button", { name: "Ask staff" }).click();
  const ask = p.getByRole("form", { name: /^Ask staff for/ });
  await ask.getByLabel("Why").fill("Found in the Depths during the last game");
  await ask.getByRole("button", { name: "Put it in the cart" }).click();

  // Asked, it is no longer refused: Spend XP sends it to the home troupe.
  await expect(line.getByText("Exception", { exact: true })).toBeVisible();
  await expect(line.getByText("Needs approval")).toBeVisible({ timeout: 15_000 });
  await expect(line).toContainText("Asked of staff: Found in the Depths during the last game");
  await expect(p.getByText("A change can't be made; see the line marked.")).toHaveCount(0);
  await p.screenshot(shots("exception-creation-only-cart"));
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Some of it waits for the home troupe's approval.")).toBeVisible();

  // The lead has it in the bell and among the approvals, which say what approving does.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}`);
  await l.getByRole("button", { name: /^Notifications, \d+ waiting$/ }).click();
  await l.getByRole("button", { name: /Silas asks for Bloodline: Creeps 0 → 2 by exception/ }).click();
  const card = l.locator("section").filter({ hasText: "Silas" }).filter({ hasText: "Bloodline: Creeps" });
  await expect(card.getByText("Exception", { exact: true })).toBeVisible();
  await expect(card).toContainText("Bloodline: Creeps 0 → 2, for 2 XP.");
  await expect(card).toContainText("Chosen after creation, by exception.");
  await expect(card).toContainText("Approving also makes Silas Nosferatu: Creeps, with its in-clan disciplines and weakness");
  await l.screenshot(shots("exception-creation-only-approval"));
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(card).toHaveCount(0);

  // Silas is of the bloodline now, as if chosen at creation.
  const sheet = await (await p.request.get(`/api/characters/${id}/sheet`)).json();
  const traits = sheet.traits as { category: string; name: string }[];
  expect(traits.find((t) => t.category === "clan")?.name).toBe("Nosferatu: Creeps");
  expect(traits.some((t) => t.name === "Bloodline: Creeps")).toBe(true);
});

test("with free changes by games played, a new character drops a skill for its full XP, which the troupe reviews", async ({ browser }) => {
  test.slow();
  const custodian = await person(browser, "freechg-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "freechg-lead");
  const player = await person(browser, "freechg-play");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Second Thoughts ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  await backstoryOptional(custodian.page, troupeId);

  // The lead gives new characters free changes for their first 3 games, in Approvals' Settings.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/approvals#settings-free-changes`);
  const settings = await tabSettings(l, "Approvals");
  const freeChanges = settings.getByRole("region", { name: "Free changes for new characters" });
  // The address opens the dialog at the card, below Backstories and Teachers, with the dialog's title still in sight.
  await expect(freeChanges.getByRole("heading", { name: "Free changes for new characters" })).toBeInViewport();
  await expect(settings.getByRole("heading", { name: "Approvals settings" })).toBeInViewport();
  await freeChanges.getByLabel(/^By games played/).check();
  await freeChanges.getByLabel("Games attended").fill("3");
  await freeChanges.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("Saved.", { exact: true })).toBeVisible();
  await expect(freeChanges.getByLabel("Games attended")).toHaveValue("3");
  await expect(freeChanges.getByRole("button", { name: "Save", exact: true })).toBeDisabled();

  // Philippa bought Stealth with XP before the troupe accepted her.
  const p = player.page;
  const id = await builtVampire(p, "Philippa", "Toreador", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]], disciplines: [["Auspex", 2], ["Celerity", 1], ["Presence", 1]] }, [
    ["skills", "Stealth", 2],
  ]);
  const asked = await p.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBe(201);
  const accepted = await l.request.post(`/api/approvals/${(await asked.json()).id}/approve`, { headers, data: {} });
  expect(accepted.status(), await accepted.text()).toBe(200);

  // Her sheet says how much of her free changes is left, and she drops Stealth for the 3 XP it cost.
  await p.goto(`/characters/${id}`);
  const free = p.getByRole("region", { name: "Free changes" });
  // The sheet takes a while on a busy server.
  await expect(free).toContainText("Free changes: 3 games left", { timeout: 15_000 });
  await expect(free).toContainText("A game counts once the character checks in.");
  // The Experience card's totals: the refund will lower Spent, not raise Earned (#548).
  const total = (name: string) => p.locator("#experience > div").filter({ hasText: name }).locator("dd").first();
  const earned = await total("Earned").innerText();
  const spent = Number(await total("Spent").innerText());
  await tapMid(p, "Lower Stealth");
  await tapMid(p, "Lower Stealth");
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  const line = cart.getByRole("listitem").filter({ hasText: "Stealth" });
  await expect(line).toContainText("A free change: 3 XP back, which the home troupe reviews.", { timeout: 15_000 });
  await expect(line).toContainText("Needs approval");
  await p.screenshot(shots("free-change-cart"));
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Some of it waits for the home troupe's approval.")).toBeVisible();
  await expect(p.getByText("Stealth 2 → 0 (a free change, 3 XP back)")).toBeVisible();

  // The lead sees it in the queue as a free change, already refunded, and approves it.
  await l.goto(`/troupes/${troupeId}/approvals`);
  const card = l.locator("section").filter({ hasText: "Philippa" });
  await expect(card.getByText("Free change", { exact: true })).toBeVisible();
  await expect(card).toContainText("Stealth 2 → 0, a free change for 3 XP back.");
  await l.screenshot(shots("free-change-approval"));
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(card).toHaveCount(0);

  await p.reload();
  await expect(p.getByText("Stealth 2 → 0 (a free change, 3 XP back)")).toHaveCount(0);
  await expect(p.locator('li[data-trait="Stealth"]')).toHaveCount(0);
  await expect(total("Spent")).toHaveText(String(spent - 3));
  await expect(total("Earned")).toHaveText(earned);
  await characterTab(p, "Experience");
  await expect(p.getByText("Stealth 2 → 0, a free change")).toBeVisible();
});

test("changes on the sheet wait in a cart, and only Spend XP makes them, all or none", async ({ browser }) => {
  const { page: p } = await person(browser, "carter");
  await p.getByLabel("Name").fill("Wren");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  // Built through the API all but one pick, which is placed from the sheet.
  const id = new URL(p.url()).pathname.split("/")[2]!;
  const put = async (url: string, data: object) => {
    const response = await p.request.put(url, { headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBe(200);
  };
  await put(`/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const build: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1]],
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, picks] of Object.entries(build))
    await put(`/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  // Opening her goes to the wizard while she's in creation (#915); the sheet is a tab of its own.
  await p.goto(`/characters/${id}/sheet`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const cart = p.getByRole("list", { name: "Changes in the cart" });

  // Creation picks go through the cart too, from the folded quick picks: placing one, and taking one back.
  await p.getByText("Quick picks (for those who know the rules)").click();
  await p.getByLabel("Pick Skills at 1").selectOption("Melee");
  await p.getByRole("button", { name: "Take back the pick on Medicine" }).click();
  await p.getByLabel("Pick Skills at 1").selectOption("Stealth");
  await expect(cart.getByRole("listitem")).toHaveText([/Take back the pick on Medicine/, /Pick Melee at 1/, /Pick Stealth at 1/]);
  await expect(p.getByRole("button", { name: "Apply picks" })).toBeEnabled();
  // The cart is kept in this browser, and leaving the page with it full asks first.
  const asked = p.waitForEvent("dialog");
  const reloaded = p.reload();
  const leaving = await asked;
  expect(leaving.type()).toBe("beforeunload");
  await leaving.accept();
  await reloaded;
  await expect(cart.getByRole("listitem")).toHaveCount(3);
  // The quick picks open by themselves while the cart holds picks from them.
  // Finishing with picks still in the cart asks what to do with them.
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByText("3 changes in the cart are not applied yet.", { exact: false })).toBeVisible();
  await p.getByRole("button", { name: "Apply them and finish" }).click();
  await expect(p.getByRole("heading", { name: "Character creation" })).toHaveCount(0);
  await expect(part("Skills").getByText("Stealth")).toBeVisible();
  await expect(part("Skills").getByText("Medicine")).toHaveCount(0);

  // Two dots of Dodge, priced dot by dot: nothing is spent yet, and the sheet shows what it would be.
  await p.getByRole("button", { name: "Raise Dodge" }).click();
  await p.getByRole("button", { name: "Raise Dodge" }).click();
  await expect(cart.getByText("Dodge 3 → 5 · 9 XP")).toBeVisible();
  await expect(p.getByLabel("3 dots, 5 after the changes in the cart")).toHaveText("3 → 5");
  await expect(p.getByText("after these changes", { exact: true })).toBeVisible();
  await expect(p.getByText("21", { exact: true })).toBeVisible();
  // Lowering it again steps the cart back.
  await p.getByRole("button", { name: "Lower Dodge" }).click();
  await expect(cart.getByText("Dodge 3 → 4 · 4 XP")).toBeVisible();
  await p.getByRole("button", { name: "Raise Dodge" }).click();

  // Archaic, then Computer, which an Archaic character cannot have: Archaic's line is refused, and nothing can be spent.
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByRole("navigation", { name: "Categories" }).getByRole("button", { name: /^Flaws/ }).click();
  await p.getByRole("combobox", { name: "Search Flaws", exact: true }).fill("Archaic");
  await p.getByRole("option", { name: /^Archaic/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  // With Archaic in the cart, the Skills panel lists nothing to take until its answer of
  // what the cart allows comes, as on a slow connection (#1032), then leaves Computer out.
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await p.route("**/api/characters/*/unavailable", async (route) => {
    await held;
    await route.continue();
  });
  await part("Skills").getByRole("button", { name: "Add" }).click();
  await p.getByRole("combobox", { name: "Search Skills", exact: true }).fill("Computer");
  await expect(p.getByRole("status", { name: "Checking what Wren can take…" })).toBeVisible();
  await expect(p.getByRole("option", { name: /^Computer/ })).toHaveCount(0);
  release();
  await p.unrouteAll({ behavior: "wait" });
  await expect(p.getByText("None you can take. 1 you can't:")).toBeVisible();
  await expect(p.getByRole("option", { name: /^Computer/ })).toHaveCount(0);
  await part("Skills").getByRole("button", { name: "Close", exact: true }).click();
  // Computer goes in from another tab, as a cart kept in this browser can: the cart refuses the pair.
  const tab = await p.context().newPage();
  await tab.goto("/");
  await tab.evaluate((key) => {
    const lines = JSON.parse(localStorage.getItem(key) ?? "[]");
    localStorage.setItem(key, JSON.stringify([...lines, { kind: "set", category: "skills", name: "Computer", detail: "", from: 0, to: 1 }]));
  }, `horatio.cart.${id}`);
  await tab.close();
  await expect(cart.getByRole("listitem").filter({ hasText: "Add Archaic" })).toContainText("An Archaic character cannot have Computer");
  await expect(cart.getByRole("listitem").filter({ hasText: "Add Computer 1" })).not.toContainText("cannot have");
  await expect(p.getByRole("button", { name: "Spend XP" })).toBeDisabled();
  await expect(p.getByText("A change can't be made; see the line marked.")).toBeVisible();
  if (test.info().project.name === "phone") {
    // Below the sheet on a phone, the cart is a tap away from the bar at the foot of the screen.
    await p.getByRole("button", { name: /^3 changes · 8 XP · \d+ XP left · Review$/ }).click();
    await expect(p.getByRole("button", { name: "Spend XP" })).toBeInViewport();
  }
  await p.screenshot(shots("cart"));
  await p.getByRole("button", { name: "Take Add Computer 1 out of the cart" }).click();
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 7 XP.")).toBeVisible(); // 9 for Dodge, less 2 for Archaic
  await expect(p.getByText("23", { exact: true })).toBeVisible();
  await expect(p.locator("li", { has: p.getByRole("button", { name: "Raise Dodge" }) }).getByLabel("5 dots", { exact: true })).toHaveText("5");
  await characterTab(p, "Experience");
  await expect(p.getByText("Dodge 3 → 5")).toBeVisible();
});

test("a plan on the Experience tab lines up two traits, priced as the cart prices them, moves one into the cart, and reprices after what the cart holds", async ({ browser }) => {
  const { page: p } = await person(browser, "planahead");
  const disciplines: [string, number][] = [["Celerity", 2], ["Potence", 1], ["Presence", 1]];
  const id = await builtVampire(p, "Thessaly", "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]], disciplines });
  await p.goto(`/characters/${id}/xp`);
  const plan = p.locator("section").filter({ has: p.getByRole("heading", { name: "Plan", exact: true }) });
  await expect(plan.getByText("Nothing planned yet.")).toBeVisible();

  // Potence, held at 1, up to 3; then Stealth, new, up to 2.
  const add = async (category: string, trait: string, upTo?: number) => {
    await plan.getByRole("button", { name: "Add to plan" }).click();
    const form = plan.getByRole("form", { name: "Add to plan" });
    await form.getByLabel("Category").selectOption({ label: category });
    await form.getByRole("combobox", { name: `Plan ${category}` }).fill(trait);
    await p.getByRole("option", { name: new RegExp(`^${trait}`) }).click();
    if (upTo) await form.getByLabel("Up to").fill(String(upTo));
    await form.getByRole("button", { name: "Add to plan" }).click();
  };
  const planned = plan.getByRole("list", { name: "Planned purchases" });
  await add("Disciplines", "Potence", 3);
  await expect(planned.getByRole("listitem")).toHaveCount(1);
  await add("Skills", "Stealth", 2);
  await expect(planned.getByRole("listitem")).toHaveText([/Potence 1 → 3 · \d+ XP · \d+ XP in all/, /Add Stealth 2 · 3 XP/]);
  await expect(planned.getByRole("listitem").first()).toContainText("Affordable now");
  const potence = (await planned.getByRole("listitem").first().textContent())!.match(/Potence 1 → 3 · (\d+) XP/)![1];
  await p.screenshot(shots("xp-plan"));

  // Reordered, Stealth first; then Potence moves into the cart, at the price the plan gave.
  await plan.getByRole("button", { name: "Move Add Stealth 2 up" }).click();
  await expect(planned.getByRole("listitem").first()).toContainText("Add Stealth 2");
  await plan.getByRole("button", { name: "Move Potence 1 → 3 to the cart" }).click();
  await expect(planned.getByRole("listitem")).toHaveCount(1);
  await expect(plan.getByText("Potence 1 → 3 is in the cart.")).toBeVisible();
  // What is left is priced after the cart, which takes Potence's XP first.
  await expect(plan.getByText(new RegExp(`after what is in the cart\\. \\d+ XP unspent, ${potence} of it for the cart`))).toBeVisible();
  await plan.getByRole("link", { name: "Spend XP on the sheet" }).click();
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  await expect(cart.getByText(`Potence 1 → 3 · ${potence} XP`)).toBeVisible();

  // A dot of Stealth goes in the cart on the sheet: the plan's line now raises it from 1, for 2 XP rather than 3.
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  await part("Skills").getByRole("button", { name: "Add" }).click();
  await p.getByRole("combobox", { name: "Search Skills", exact: true }).fill("Stealth");
  await p.getByRole("option", { name: /^Stealth/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await expect(cart.getByText("Add Stealth 1 · 1 XP")).toBeVisible();
  await characterTab(p, "Experience");
  await expect(planned.getByRole("listitem")).toHaveText([/^Stealth 1 → 2 · 2 XP · 2 XP in all/]);
});

test("a cart is judged by the sheet it ends with, so a technique may go in before what it needs", async ({ browser }) => {
  const { page: p } = await person(browser, "tactician");
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Kestrel" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const build: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, picks] of Object.entries(build))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});

  // Fearful Blow (Potence 2 and Presence 2) is in the cart before the dots it needs, as a cart kept from an earlier visit might be.
  const lines = [
    { kind: "set", category: "techniques", name: "Fearful Blow", detail: "", from: 0, to: 1, fixed: true },
    { kind: "set", category: "disciplines", name: "Potence", detail: "", from: 1, to: 2 },
    { kind: "set", category: "disciplines", name: "Presence", detail: "", from: 1, to: 2 },
  ];
  await p.evaluate(([key, value]) => localStorage.setItem(key, value), [`horatio.cart.${id}`, JSON.stringify(lines)]);
  await p.goto(`/characters/${id}`);
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  // Each line is priced as if the ones above it were made, and none is refused.
  await expect(cart.getByRole("listitem")).toHaveText([/Add Fearful Blow.* · 12 XP/, /Potence 1 → 2 · 6 XP/, /Presence 1 → 2 · 6 XP/]);
  await expect(p.getByText("A change can't be made; see the line marked.")).toHaveCount(0);

  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 24 XP.")).toBeVisible();
  await expect(p.locator("main").getByText("Fearful Blow", { exact: true })).toBeVisible();
});

test("a Neonate Crusader with Hard as Steel buys one Fortitude elder power through the cart, for 20 XP", async ({ browser }) => {
  const { page: p } = await person(browser, "steel-crusader");
  // A Neonate (Generation 1), whose blood is too thin for elder powers but for the one Hard as Steel opens.
  const id = await builtVampire(
    p,
    "Godfrey",
    "Ventrue: Crusader",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]], disciplines: [["Fortitude", 2], ["Auspex", 1], ["Dominate", 1]] },
    [
      ["disciplines", "Fortitude", 5],
      ["merits", "Hard as Steel", 3],
    ],
  );
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const disciplines = part("Disciplines");
  const chips = p.getByRole("navigation", { name: "Categories" });
  const cart = p.getByRole("list", { name: "Changes in the cart" });

  // The picker offers Fortitude's elder powers at the merit's price, and no others.
  await disciplines.getByRole("button", { name: "Add" }).click();
  await chips.getByRole("button", { name: /^Elder Disciplines/ }).click();
  const elder = await addList(p, "Elder Disciplines");
  const armor = elder.getByRole("option", { name: /^Fortitude: Personal Armor/ });
  await expect(armor).toBeEnabled();
  await expect(armor).toContainText("Hard as Steel: 20 XP");
  await expect(elder.getByRole("option", { name: /^Celerity: / })).toHaveCount(0);
  // Priced as it is chosen, with no button to press.
  await armor.click();
  await expect(p.getByText("Hard as Steel: 20 XP.", { exact: true })).toBeVisible();
  await p.getByRole("button", { name: "Add to cart" }).click();
  const line = cart.getByRole("listitem").filter({ hasText: "Add Fortitude: Personal Armor" });
  await expect(line).toContainText("20 XP");
  await expect(line).toContainText("Hard as Steel: 20 XP");

  // One only: with it in the cart, a second is refused, with the reason.
  await disciplines.getByRole("button", { name: "Add" }).click();
  await chips.getByRole("button", { name: /^Elder Disciplines/ }).click();
  await p.getByLabel("Show").selectOption({ label: "Everything" });
  await p.getByRole("combobox", { name: "Search Elder Disciplines", exact: true }).fill("Resilient Mind");
  await expect(p.getByRole("option", { name: /^Fortitude: Resilient Mind/ })).toBeDisabled();
  await expect(p.getByText("A Neonate's or Ancilla's blood is too thin for elder powers.", { exact: false })).toBeVisible();
  await p.screenshot(shots("opened-power"));

  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 20 XP.")).toBeVisible();
  // The sheet says which power the merit opened.
  await expect(disciplines.getByText("through Hard as Steel")).toBeVisible();
  await expect(part("Merits and Flaws").getByText("opened Fortitude: Personal Armor")).toBeVisible();
});

test("in the picker, a technique, an elder power and a discipline open to say what they do, greyed or not, choosing none", async ({ browser }) => {
  const { page: p } = await person(browser, "power-reader");
  // A Neonate, whose blood is too thin for elder powers: they are greyed, but can still be read (#1000).
  const id = await builtVampire(p, "Wilhelmina", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Potence", 2], ["Celerity", 1], ["Presence", 1]],
  });
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const disciplines = part("Disciplines");
  const chips = p.getByRole("navigation", { name: "Categories" });

  // A technique's chevron shows what it does under the list, one at a time, choosing none.
  const about = aboutChoice(p);
  await disciplines.getByRole("button", { name: "Add" }).click();
  await chips.getByRole("button", { name: /^Techniques/ }).click();
  await p.getByLabel("Show").selectOption({ label: "Everything" });
  await p.getByRole("combobox", { name: "Search Techniques", exact: true }).fill("Re");
  await p.getByRole("button", { name: "About Relentless Pursuit" }).click();
  await expect(about).toContainText("when someone you're in melee with moves away, move up to 12 steps after them");
  await expect(about.getByText("MET: VTM p. 231")).toBeVisible();
  await p.getByRole("button", { name: "About Retain the Quick Blood" }).click();
  await expect(about).toContainText("when you spend Blood on a Quietus power, regain 1 of it");
  await expect(about).not.toContainText("when someone you're in melee with moves away");
  await expect(p.getByRole("button", { name: "Add to cart" })).toHaveCount(0);
  // Closed again with the same chevron.
  await p.getByRole("button", { name: "About Retain the Quick Blood" }).click();
  await expect(about).not.toContainText("when you spend Blood on a Quietus power");

  // On a phone: an elder power the rules refuse is greyed, and still opens.
  await p.setViewportSize({ width: 375, height: 800 });
  await chips.getByRole("button", { name: /^Elder Disciplines/ }).click();
  await p.getByLabel("Show").selectOption({ label: "Everything" });
  await p.getByRole("combobox", { name: "Search Elder Disciplines", exact: true }).fill("Crimson Fury");
  await expect(p.getByRole("option", { name: /^Animalism: Crimson Fury/ })).toBeDisabled();
  await p.getByRole("button", { name: "About Animalism: Crimson Fury" }).click();
  await expect(about).toContainText("flees in a fear frenzy Willpower can't stop");
  await expect(about.getByText("MET: VTM p. 212")).toBeVisible();
  await expect(p.getByRole("button", { name: "Add to cart" })).toHaveCount(0);
  // Nothing runs off the side of the screen.
  expect(await p.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);

  // A discipline not held yet: the power its first dot gives, and its test.
  await chips.getByRole("button", { name: /^Disciplines/ }).click();
  await p.getByLabel("Show").selectOption({ label: "Everything" });
  await p.getByRole("combobox", { name: "Search Disciplines", exact: true }).fill("Auspex");
  await p.getByRole("button", { name: "About Auspex" }).click();
  await expect(about.getByText("Dot 1 gives:")).toBeVisible();
  await expect(about.getByText("Heightened Senses", { exact: true })).toBeVisible();
  await expect(about.getByText("Test: Mental + Investigation against Mental + Willpower.")).toBeVisible();
  await p.screenshot(shots("power-info"));

  // A held one says, under its name on the sheet, what its next dot would give.
  await disciplines.getByRole("button", { name: "Close" }).click();
  await disciplines.getByRole("button", { name: "Potence", exact: true }).click();
  await expect(disciplines.getByText("Dot 3 gives:")).toBeVisible();
});

test("in the cart, a second Retainer and a second Alternate Identity are each bought on their own, by name", async ({ browser }) => {
  const { page: p } = await person(browser, "twofold-player");
  const headers = { "X-Horatio": "1" };
  const send = async (method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  // Ysolde starts with Bocephus as a Retainer at 3 and one cover identity at 2, at Generation 1.
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Ysolde" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Nosferatu", rating: null });
  const picks: Record<string, [string, number, string?][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Stealth", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Retainers", 3, "Bocephus"], ["Alternate Identity", 2, "Dr. Ellen Marsh, coroner"], ["Generation", 1]],
    disciplines: [["Animalism", 2], ["Obfuscate", 1], ["Potence", 1]],
  };
  for (const [category, list] of Object.entries(picks))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating, detail]) => ({ name: n, rating, detail: detail ?? "" })) });
  await send("POST", `/api/characters/${id}/creation/complete`);

  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  // A second Retainer is bought from under Bocephus's row, where the sheet says what the dots are (#586).
  // It is named as it goes in, and priced from its own first dot: 1 + 2 at Generation 1.
  await expect(part("Backgrounds").getByText("Each Retainer is bought on its own; its dots are how capable it is.")).toBeVisible();
  await part("Backgrounds").getByRole("button", { name: "Buy another Retainer" }).click();
  await expect(p.getByText("Each Retainer is bought on its own, with its own dots, up to 5.")).toBeVisible();
  await p.getByPlaceholder("Such as Bocephus").fill("Rook");
  await p.getByLabel("Rating").fill("2");
  await p.getByRole("button", { name: "Add to cart" }).click();
  await expect(cart.getByText("Add Retainers: Rook 2 · 3 XP")).toBeVisible();
  // And a second identity, by its own name.
  await part("Backgrounds").getByRole("button", { name: "Add" }).click();
  await p.getByRole("combobox", { name: "Search Backgrounds", exact: true }).fill("Alternate");
  // The panel lists it once checked.
  await expect(p.getByRole("combobox", { name: "Search Backgrounds", exact: true })).toHaveAttribute("placeholder", /you can take/);
  await p.getByRole("option", { name: /^Alternate Identity/ }).click();
  await p.getByPlaceholder("Such as Dr. Ellen Marsh, coroner").fill("Father Kell");
  await p.getByRole("button", { name: "Add to cart" }).click();
  await expect(cart.getByText("Add Alternate Identity: Father Kell 1 · 1 XP")).toBeVisible();
  // Bocephus's fourth dot costs his own next dot, though it is the sixth Retainer dot in all.
  await p.getByRole("button", { name: "Raise Retainers: Bocephus" }).click();
  await expect(cart.getByText("Retainers: Bocephus 3 → 4 · 4 XP")).toBeVisible();
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 8 XP.")).toBeVisible();

  // Each is on the sheet by name, with its own dots.
  const backgrounds = part("Backgrounds");
  for (const name of ["Retainers: Bocephus", "Retainers: Rook", "Alternate Identity: Dr. Ellen Marsh, coroner", "Alternate Identity: Father Kell"])
    await expect(backgrounds.getByRole("button", { name: `Raise ${name}`, exact: true })).toBeVisible();
  // Each is listed under its own row.
  for (const name of ["Bocephus", "Rook"]) await expect(p.getByLabel(`Retainer: ${name}`, { exact: true }).getByRole("listitem")).toHaveCount(1);

  // Bocephus is a ghoul, with three skills and Obfuscate as his specialties (p. 105).
  const list = p.getByLabel("Retainer: Bocephus", { exact: true });
  await list.getByRole("button", { name: "Edit Bocephus" }).click();
  await list.getByLabel("Bocephus is a ghoul").check();
  for (const skill of ["Brawl", "Stealth", "Dodge"]) await list.getByLabel("Add a specialty for Bocephus").selectOption(skill);
  await list.getByLabel("Discipline for Bocephus").selectOption("Obfuscate");
  await expect(list.getByText("Specialties 4 of 4:")).toBeVisible();
  await list.getByRole("button", { name: "Save Retainer" }).click();
  await expect(list.getByText("Brawl, Stealth, Dodge, Obfuscate")).toBeVisible();
  // Father Kell is Accepted by the Sabbat; each identity says what its rating stands up to.
  await p.getByRole("button", { name: "Accepted by a sect or group?" }).last().click();
  await p.getByLabel("Who Accepts Father Kell").fill("the Sabbat");
  await p.getByRole("button", { name: "Save", exact: true }).click();
  await expect(p.getByLabel("About Father Kell")).toContainText("Accepted by the Sabbat.");
  await expect(p.getByLabel("About Dr. Ellen Marsh, coroner")).toContainText("Well grounded");

  // On the Play View, each Retainer has a pool of its own, and its health and Blood to tap.
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Tracker" }).click();
  const bocephus = p.getByRole("article", { name: "Retainer: Bocephus" });
  const rook = p.getByRole("article", { name: "Retainer: Rook" });
  await expect(bocephus.getByLabel("Bocephus's pool: 8")).toBeVisible();
  await expect(rook.getByLabel("Rook's pool: 4")).toBeVisible();
  await expect(bocephus.getByRole("listitem").filter({ hasText: "Brawl" })).toContainText("13");
  await expect(bocephus.getByRole("listitem").filter({ hasText: "Vanish From the Mind's Eye" }).getByLabel("4 dots")).toBeVisible();
  await expect(bocephus.getByText("Cloak the Gathering")).toHaveCount(0);
  await expect(rook.getByText("Blood")).toHaveCount(0);
  await p.getByRole("checkbox", { name: "Quick notes" }).uncheck();
  await bocephus.getByRole("button", { name: "Spend Bocephus: Blood" }).click();
  await expect(bocephus.getByLabel("Bocephus: Blood: 4 of 5")).toBeVisible();
  await rook.getByRole("button", { name: "Spend Rook: health" }).click();
  await expect(rook.getByLabel("Rook: health: 1 of 2")).toBeVisible();

  // And on the Sheet tab, both identities by name, with who Accepts one.
  await p.getByRole("tab", { name: "Sheet" }).click();
  await expect(p.getByText("Alternate Identity: Dr. Ellen Marsh, coroner")).toBeVisible();
  await expect(p.getByText("Alternate Identity: Father Kell")).toBeVisible();
  await expect(p.getByText("Accepted by the Sabbat.")).toBeVisible();
});
