import { expect, test } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, builtVampire, ATTRIBUTES_AND_FOCUSES, backstoryOptional, characterTab, tapMid } from "./support";

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
  await p.locator("main").getByRole("link", { name: "Experience", exact: true }).click();
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
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Merits").fill("Ventrue Royalty");
  await p.getByRole("button", { name: /^Ventrue Royalty/ }).click();
  await expect(p.getByText("Choose your free backgrounds")).toBeVisible();
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

  // Until a troupe accepts her, the choices change freely: Haven in place of Resources.
  await p.getByRole("button", { name: "Change the free traits for Ventrue Royalty" }).click();
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
  await expect(p.getByRole("button", { name: "Change the free traits for Ventrue Royalty" })).toHaveCount(0);
  const refused = await p.request.fetch(`/api/characters/${id}/traits/choices`, {
    method: "PUT",
    headers,
    data: { category: "merits", name: "Ventrue Royalty", detail: "", picks: [] },
  });
  expect(refused.status()).toBe(409);
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
  await p.getByLabel("Search Merits").fill("Rugged");
  await p.getByRole("button", { name: /^Rugged/ }).click();
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
  await p.locator("main").getByRole("link", { name: "Experience", exact: true }).click();
  await expect(p.getByText("Rugged 3 → 0 (declined)")).toBeVisible();
  await expect(p.getByText("Low Pain Threshold 3 → 0", { exact: true })).toBeVisible();
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

  // The lead gives new characters free changes for their first 3 games, under Rules.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/rules/free-changes`);
  await l.getByRole("button", { name: "Change free changes" }).click();
  await l.getByLabel(/^By games played/).check();
  await l.getByLabel("Games attended").fill("3");
  await l.getByRole("button", { name: "Save" }).click();
  await expect(l.getByText("Until a character has attended 3 games after the troupe accepts it.")).toBeVisible();

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
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const cart = p.getByRole("list", { name: "Changes in the cart" });

  // Creation picks go through the cart too: placing one, and taking one back.
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
  await p.getByLabel("Search Flaws").fill("Archaic");
  await p.getByRole("button", { name: /^Archaic/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await part("Skills").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Skills").fill("Computer");
  await p.getByRole("button", { name: /^Computer/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
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
  await p.locator("main").getByRole("link", { name: "Experience", exact: true }).click();
  await expect(p.getByText("Dodge 3 → 5")).toBeVisible();
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
  const armor = p.getByRole("button", { name: /^Fortitude: Personal Armor/ });
  await expect(armor).toBeEnabled();
  await expect(armor).toContainText("Hard as Steel: 20 XP");
  await expect(p.getByRole("button", { name: /^Celerity: / })).toHaveCount(0);
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
  await p.getByLabel("Search Elder Disciplines").fill("Resilient Mind");
  await expect(p.getByRole("button", { name: /^Fortitude: Resilient Mind/ })).toBeDisabled();
  await expect(p.getByText("A Neonate's or Ancilla's blood is too thin for elder powers.", { exact: false })).toBeVisible();
  await p.screenshot(shots("opened-power"));

  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 20 XP.")).toBeVisible();
  // The sheet says which power the merit opened.
  await expect(disciplines.getByText("through Hard as Steel")).toBeVisible();
  await expect(part("Merits and Flaws").getByText("opened Fortitude: Personal Armor")).toBeVisible();
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
  // A second Retainer is named as it goes in, and priced from its own first dot: 1 + 2 at Generation 1.
  await part("Backgrounds").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Backgrounds").fill("Retainers");
  await p.getByRole("button", { name: "Retainers" }).first().click();
  await expect(p.getByText("Each Retainer is bought on its own, with its own dots, up to 5.")).toBeVisible();
  await p.getByPlaceholder("Such as Bocephus").fill("Rook");
  await p.getByLabel("Rating").fill("2");
  await p.getByRole("button", { name: "Add to cart" }).click();
  await expect(cart.getByText("Add Retainers: Rook 2 · 3 XP")).toBeVisible();
  // And a second identity, by its own name.
  await part("Backgrounds").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Backgrounds").fill("Alternate");
  await p.getByRole("button", { name: "Alternate Identity" }).first().click();
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
  await expect(p.getByLabel("Retainers list").getByRole("listitem")).toHaveCount(2);

  // Bocephus is a ghoul, with three skills and Obfuscate as his specialties (p. 105).
  const list = p.getByLabel("Retainers list");
  await list.getByRole("button", { name: "Edit Retainers" }).click();
  await list.getByLabel("Bocephus is a ghoul").check();
  for (const skill of ["Brawl", "Stealth", "Dodge"]) await list.getByLabel("Add a specialty for Bocephus").selectOption(skill);
  await list.getByLabel("Discipline for Bocephus").selectOption("Obfuscate");
  await expect(list.getByText("Specialties 4 of 4:")).toBeVisible();
  await list.getByRole("button", { name: "Save Retainers" }).click();
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
  await expect(bocephus.getByText("4. Vanish From the Mind's Eye")).toBeVisible();
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
