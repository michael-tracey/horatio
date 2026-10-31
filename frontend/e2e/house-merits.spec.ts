import { expect, test } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, undoInHeader, characterTab } from "./support";

/** A troupe's own merits, what they do on the sheet, and using them at a game. */

closeContextsAfterEach();

test("a troupe's own merits: staff only, or taken when building for it, and marked ★ as the troupe's", async ({ browser }) => {
  const custodian = await person(browser, "hm-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "hm-lead");
  const player = await person(browser, "hm-player");
  const troupeName = `Court of Stars ${run}`;
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  const mark = `House merit of ${troupeName}`;

  // The lead makes two on the Rules tab: one only staff give, one players can take when building.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/rules/house-traits`);
  const addOne = async (name: string, points: string, availability: string, description: string) => {
    await l.getByRole("button", { name: "Add a merit or flaw" }).click();
    await l.getByLabel("Name").fill(name);
    await l.getByLabel("Points").selectOption(points);
    await l.getByLabel(availability).check();
    await l.getByLabel("Description").fill(description);
    await l.getByRole("button", { name: "Add the merit" }).click();
    await expect(l.getByRole("listitem").filter({ hasText: name })).toBeVisible();
  };
  await addOne("Favour of the Crossroads", "2", "Given by staff only", "The Prince owes you one.");
  await addOne("Child of the Stars", "1", "Available when building for the troupe", "Born under a lucky sign.");
  await expect(l.getByRole("listitem").filter({ hasText: "Favour of the Crossroads" })).toContainText(mark);
  await l.screenshot(shots("house-traits"));

  // Lune is built for the troupe through the API, and visits it so its staff see her.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const build = async (name: string, buildingFor: string | null) => {
    const { id } = await send("POST", "/api/characters", { splat: "vampire", name, building_troupe_id: buildingFor });
    await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
      disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
    };
    for (const [category, list] of Object.entries(picks))
      await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send("POST", `/api/characters/${id}/creation/complete`, {});
    await send("POST", `/api/characters/${id}/troupes`, { troupe_id: troupeId });
    return id as string;
  };
  const lune = await build("Lune", troupeId);

  // Building for the troupe, she is offered the one players can take, not the one staff give.
  await p.goto(`/characters/${lune}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Merits").fill("Favour of the");
  await expect(p.getByRole("button", { name: /^Favour of the Crossroads/ })).toHaveCount(0);
  await p.getByLabel("Search Merits").fill("Child of the");
  await expect(p.getByRole("button", { name: /^Child of the Stars/ })).toContainText(mark);
  await p.getByRole("button", { name: /^Child of the Stars/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(part("Merits and Flaws")).toContainText("Child of the Stars");
  await expect(part("Merits and Flaws")).toContainText(`★${mark}`);

  // The lead gives her the staff-only one, free, with a reason.
  await l.goto(`/characters/${lune}`);
  const house = l.locator("section").filter({ has: l.getByRole("heading", { name: "House merits and flaws", exact: true }) });
  await house.getByRole("button", { name: "Apply Favour of the Crossroads" }).click();
  await house.getByLabel("Reason").fill("Saved the Prince's ghoul");
  await house.getByRole("button", { name: "Apply Favour of the Crossroads" }).click();
  const merits = l.locator("section").filter({ has: l.getByRole("heading", { name: "Merits and Flaws", exact: true }) });
  await expect(merits).toContainText("Favour of the Crossroads");
  await expect(merits).toContainText("given by staff, free");
  await l.screenshot(shots("house-traits-applied"));
  await p.reload();
  await expect(part("Merits and Flaws")).toContainText("Favour of the Crossroads");
  await characterTab(p, "Log");
  await expect(p.getByText(/the house merit of .* ★ Favour of the Crossroads \(free\): Saved the Prince's ghoul/)).toBeVisible();

  // A character only visiting the troupe is offered neither, by the player's list or by staff.
  const visitor = await build("Isaure", null);
  await p.goto(`/characters/${visitor}`);
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Merits").fill("Child of the");
  await expect(p.getByRole("button", { name: /^Child of the Stars/ })).toHaveCount(0);
  await l.goto(`/characters/${visitor}`);
  await expect(l.getByRole("heading", { name: "Attributes", exact: true })).toBeVisible();
  await expect(l.getByRole("heading", { name: "House merits and flaws", exact: true })).toHaveCount(0);
});

test("a house merit's effects: the ST builds Old Money from blocks, previews it, and a player taking it gets Resources 2 free", async ({ browser }) => {
  const custodian = await person(browser, "om-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "om-lead");
  const player = await person(browser, "om-player");
  const troupeName = `Hall of Ledgers ${run}`;
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  const summary = "The first 2 dots of Resources are free. Needs Resources 1 or more.";

  // The lead makes it from blocks: the first 2 dots of Resources free, and Resources 1 or more needed.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/rules/house-traits`);
  await l.getByRole("button", { name: "Add a merit or flaw" }).click();
  await l.getByLabel("Name").fill("Old Money");
  await l.getByLabel("Points").selectOption("2");
  await l.getByLabel("Available when building for the troupe").check();
  await l.getByLabel("Description").fill("The family fortune, still in trust.");
  await l.getByRole("button", { name: "Add an effect" }).click();
  await expect(l.getByLabel("Effect 1: what it does")).toHaveValue("free");
  await l.getByLabel("Effect 1: kind of trait").selectOption("backgrounds");
  await l.getByLabel("Effect 1: add a trait").selectOption("Resources");
  await l.getByLabel("Effect 1: free dots").selectOption("2");
  await l.getByRole("button", { name: "Add an effect" }).click();
  await l.getByLabel("Effect 2: what it does").selectOption("requires");
  await l.getByLabel("Effect 2: what it asks about").selectOption("trait");
  await l.getByLabel("Effect 2: kind of trait").selectOption("backgrounds");
  await l.getByLabel("Effect 2: trait").selectOption("Resources");
  await l.getByLabel("Effect 2: at least").selectOption("1");

  // The preview tries it on a new character before it is saved.
  const preview = l.getByRole("region", { name: "Preview" });
  await expect(preview).toContainText(`What it does: ${summary}`);
  await expect(preview).toContainText("Resources: 0 → 2, all free.");
  await expect(preview).toContainText("Met: Old Money: needs Resources 1 or more.");
  await l.screenshot(shots("house-effects-preview"));
  await l.getByRole("button", { name: "Add the merit" }).click();
  await expect(l.getByRole("listitem").filter({ hasText: "Old Money" })).toContainText(`What it does: ${summary}`);

  // Philippa is built for the troupe, and takes it from the sheet's list.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Philippa", building_troupe_id: troupeId });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const picks: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, list] of Object.entries(picks))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});

  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Merits").fill("Old Money");
  await expect(p.getByRole("button", { name: /^Old Money/ })).toContainText(`What it does: ${summary}`);
  await p.getByRole("button", { name: /^Old Money/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await p.getByRole("button", { name: "Spend XP" }).click();

  // On the sheet: Resources 2, given by the merit, and the merit marked ★ with what it does.
  const merits = part("Merits and Flaws");
  await expect(merits).toContainText(`★House merit of ${troupeName}`);
  await merits.getByRole("button", { name: "Old Money", exact: true }).click();
  await expect(merits).toContainText("The family fortune, still in trust.");
  await expect(merits).toContainText(`What it does: ${summary}`);
  const resources = part("Backgrounds").locator("div").filter({ hasText: /^Resources/ }).first();
  await expect(resources).toContainText("+2 from Old Money");
  await p.screenshot(shots("house-effects-sheet"));
});

test("a house merit in play: the ST makes Battle Trance, a switch and a use a game, and its holder switches it on and undoes it", async ({ browser }) => {
  const custodian = await person(browser, "trance-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "trance-lead");
  const player = await person(browser, "trance-player");
  const troupeName = `Ring of Embers ${run}`;
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  const summary = "Switched on in play: +2 to Brawl attacks and −2 to Mental pools. 1 use a game.";

  // The lead makes it from blocks: switched on in play, +2 on Brawl and −2 on Mental pools, and 1 use a game.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/rules/house-traits`);
  await l.getByRole("button", { name: "Add a merit or flaw" }).click();
  await l.getByLabel("Name").fill("Battle Trance");
  await l.getByLabel("Points").selectOption("2");
  await l.getByLabel("Given by staff only").check();
  await l.getByLabel("Description").fill("The red haze, called up at will.");
  await l.getByRole("button", { name: "Add an effect" }).click();
  await l.getByLabel("Effect 1: what it does").selectOption("switch");
  await l.getByLabel("Effect 1: change 1 amount").selectOption("2");
  await l.getByLabel("Effect 1: change 1 pool").selectOption("attack:Brawl");
  await l.getByRole("button", { name: "Effect 1: add a change" }).click();
  await l.getByLabel("Effect 1: change 2 amount").selectOption("-2");
  await l.getByLabel("Effect 1: change 2 pool").selectOption("attribute:Mental");
  await l.getByRole("button", { name: "Add an effect" }).click();
  await l.getByLabel("Effect 2: what it does").selectOption("uses");
  await expect(l.getByLabel("Effect 2: uses a game")).toHaveValue("1");
  const preview = l.getByRole("region", { name: "Preview" });
  await expect(preview).toContainText(`What it does: ${summary}`);
  await expect(preview).toContainText("A switch on the Play View, Battle Trance: +2 Brawl attacks, -2 Mental.");
  await expect(preview).toContainText("1 use a game, under Uses this game on the Play View.");
  await l.screenshot(shots("house-play-preview"));
  await l.getByRole("button", { name: "Add the merit" }).click();
  await expect(l.getByRole("listitem").filter({ hasText: "Battle Trance" })).toContainText(`What it does: ${summary}`);

  // Sigrun is built for the troupe and visits it; the lead gives her Battle Trance.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Sigrun", building_troupe_id: troupeId });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const picks: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, list] of Object.entries(picks))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});
  await send("POST", `/api/characters/${id}/troupes`, { troupe_id: troupeId });
  const houseTraits = await (await l.request.get(`/api/troupes/${troupeId}/house-traits`)).json();
  const trance = houseTraits.find((h: { name: string }) => h.name === "Battle Trance");
  const applied = await l.request.post(`/api/characters/${id}/house-traits`, {
    headers,
    data: { house_trait_id: trance.id, free: true, reason: "Blooded at the Embers" },
  });
  expect(applied.status(), await applied.text()).toBe(200);

  // On her Play View, the drawer has the switch; switched on, the unarmed attack gains 2.
  await p.goto(`/play/characters/${id}?tab=pools`);
  await expect(p.getByRole("heading", { name: "Sigrun" })).toBeVisible();
  const unarmed = p.getByRole("listitem").filter({ hasText: /^Unarmed attack/ });
  await expect(unarmed).toContainText("Physical 7 + Brawl 4 + Potence 2");
  await expect(unarmed.getByText("13", { exact: true })).toBeVisible();
  await expect(unarmed).not.toContainText("Battle Trance");
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  const on = p.getByLabel("Battle Trance on");
  await expect(on).not.toBeChecked();
  await expect(p.getByText("+2 Brawl attacks · -2 Mental")).toBeVisible();
  await on.check();
  await expect(unarmed).toContainText("Physical 7 + Brawl 4 + Potence 2 + Battle Trance 2");
  await expect(unarmed.getByText("15", { exact: true })).toBeVisible();
  await expect(p.getByRole("region", { name: "Switched on now" })).toContainText("On: Battle Trance");
  await p.screenshot(shots("house-play-switch"));

  // Undo, in the header, switches it off again.
  await p.getByRole("tab", { name: "Tracker" }).click();
  await (await undoInHeader(p, "Battle Trance on")).click();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await expect(p.getByRole("region", { name: "Switched on now" })).toHaveCount(0);

  // Uses this game has Battle Trance, with its one use.
  const uses = p.locator("section").filter({ has: p.getByRole("heading", { name: "Uses this game" }) });
  const row = uses.getByRole("listitem").filter({ hasText: "Battle Trance" });
  await expect(row).toContainText("1 of 1 left");
  await p.getByRole("tab", { name: "Pools" }).click();
  await expect(unarmed).not.toContainText("Battle Trance");
  await expect(unarmed.getByText("13", { exact: true })).toBeVisible();
});
