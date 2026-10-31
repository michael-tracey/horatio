import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, ATTRIBUTES_AND_FOCUSES, backstoryOptional } from "./support";

/** Equipment: giving it, reading it, equipping it and finding it. */

closeContextsAfterEach();

test("a troupe gives equipment: a dagger from a template, a rifle by hand, refused when it breaks the rules, and a special blade from the character's page", async ({ browser }) => {
  const custodian = await person(browser, "equip-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "equip-lead");
  const assistant = await person(browser, "equip-assistant");
  const player = await person(browser, "equip-player");
  const headers = { "X-Horatio": "1" };
  const call = (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => page.request.fetch(url, { method, headers, data });
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await call(page, method, url, data);
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Armoury ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/staff`, { handle: assistant.handle, role: "assistant_storyteller" });

  // Agnes is at home in the troupe; Vera only visits it.
  const build = async (name: string, home: boolean) => {
    const { id } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name });
    await send(player.page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Haven", 2], ["Generation", 1]],
      disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
    };
    for (const [category, list] of Object.entries(picks))
      await send(player.page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send(player.page, "POST", `/api/characters/${id}/creation/complete`);
    if (home) {
      const asked = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
      await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    } else {
      await send(player.page, "POST", `/api/characters/${id}/troupes`, { troupe_id: troupe.id });
    }
    return id as string;
  };
  const agnes = await build("Agnes", true);
  const vera = await build("Vera", false);
  // An NPC of the troupe's, holding a stake.
  const bram = await send(lead.page, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Bram" });
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/equipment`, {
    character_id: bram.id,
    name: "Wooden Stake",
    kind: "melee",
    grade: "standard",
    qualities: [{ name: "Concealable" }, { name: "Staking" }],
  });

  // The lead gives Agnes the book's Silver Dagger from the troupe's Equipment tab.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}`);
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: "Equipment", exact: true }).click();
  await l.getByRole("button", { name: "Give equipment" }).click();
  let form = l.getByRole("form", { name: "Give equipment" });
  await form.getByLabel("Character").selectOption({ label: "Agnes (equip-player)" });
  await form.getByLabel("Start from").selectOption({ label: "Silver Dagger" });
  await expect(form.getByLabel("Name", { exact: true })).toHaveValue("Silver Dagger");
  await expect(form.getByRole("list", { name: "Qualities chosen" })).toContainText("Concealable");
  await expect(form.getByLabel("What it is")).toHaveText("1 hand · 1 damage · range 2 steps");
  await form.getByRole("button", { name: "Give to Agnes" }).click();
  await expect(l.getByText("Given Silver Dagger.")).toBeVisible();

  // And a hunting rifle by hand. Quick Draw breaks the rules, and is refused.
  await l.getByRole("button", { name: "Give equipment" }).click();
  form = l.getByRole("form", { name: "Give equipment" });
  await form.getByLabel("Character").selectOption({ label: "Agnes (equip-player)" });
  await form.getByLabel("Name", { exact: true }).fill("Hunting rifle");
  await form.getByLabel("Kind").selectOption({ label: "Ranged weapon" });
  for (const quality of ["Accurate", "Long Range", "Quick Draw"]) await form.getByLabel("Add a quality").selectOption({ label: quality });
  await expect(form.getByRole("list", { name: "Rules it breaks" })).toContainText("Long Range needs two hands, so it can't be Quick Draw.");
  await form.getByRole("button", { name: "Give to Agnes" }).click();
  await expect(form.getByRole("alert")).toContainText("Long Range needs two hands, so it can't be Quick Draw.");
  await form.getByRole("button", { name: "Remove Quick Draw" }).click();
  await expect(form.getByRole("list", { name: "Rules it breaks" })).toHaveCount(0);
  await expect(form.getByLabel("What it is")).toHaveText("2 hands · 2 damage · 12 shots · range half a mile");
  await form.getByRole("button", { name: "Give to Agnes" }).click();
  await expect(l.getByText("Given Hunting rifle.")).toBeVisible();

  // The API refuses giving to the visiting Vera, and lets no player give or change.
  const visiting = await call(l, "POST", `/api/troupes/${troupe.id}/equipment`, { character_id: vera, name: "Knife", kind: "melee", grade: "cheap", qualities: [] });
  expect(visiting.status()).toBe(422);
  expect((await visiting.json()).detail).toContain("not Vera's home troupe");

  // The assistant makes a special blade from Agnes's page: four qualities and an effect of the troupe's.
  const a = assistant.page;
  await a.goto(`/characters/${agnes}`);
  await a.getByRole("button", { name: "Give equipment" }).click();
  form = a.getByRole("dialog").getByRole("form", { name: "Give equipment" });
  await form.getByLabel("Name", { exact: true }).fill("Blade of Saulot");
  await form.getByLabel("Grade").selectOption({ label: "Special (any number)" });
  for (const quality of ["Accurate", "Concealable", "Silver", "Masterwork"]) await form.getByLabel("Add a quality").selectOption({ label: quality });
  await form.getByLabel("Masterwork detail (optional)").fill("cuts through chains");
  await form.getByRole("button", { name: "Add a special effect" }).click();
  await form.getByLabel("Effect 1", { exact: true }).fill("Drinks the Blood");
  await form.getByLabel("What effect 1 does").fill("Once a game, heal 1 normal damage when it draws blood.");
  await expect(form.getByRole("list", { name: "Rules it breaks" })).toHaveCount(0);
  await form.getByRole("button", { name: "Give to Agnes" }).click();
  await expect(a.getByText("Gave Agnes Blade of Saulot.")).toBeVisible();

  const p = player.page;
  const blade = (await (await p.request.get(`/api/characters/${agnes}/equipment`)).json()).items.find((i: { name: string }) => i.name === "Blade of Saulot");
  expect(blade.special).toBe(true);
  expect(blade.staff_note).toBeNull();
  const made = await call(p, "POST", `/api/troupes/${troupe.id}/equipment`, { character_id: agnes, name: "Mine", kind: "melee", grade: "special", qualities: [] });
  expect(made.status()).toBe(403);
  const changed = await call(p, "PUT", `/api/troupes/${troupe.id}/equipment/${blade.id}`, { name: "Mine", kind: "melee", grade: "special", qualities: [], reason: "Mine" });
  expect(changed.status()).toBe(403);
  const told = (await (await p.request.get("/api/notifications")).json()).items.map((i: { summary: string }) => i.summary);
  expect(told).toContain("equip-lead gave Agnes Silver Dagger (melee weapon: Concealable, Silver).");

  // The troupe's tab lists them all; filtering by holder and kind finds the dagger.
  await l.reload();
  const held = l.getByRole("list", { name: "Equipment", exact: true });
  for (const name of ["Silver Dagger", "Hunting rifle", "Blade of Saulot"]) await expect(held.getByRole("listitem", { name: `${name}, held by Agnes` })).toBeVisible();
  await expect(held.getByRole("listitem", { name: "Wooden Stake, held by Bram" })).toBeVisible();
  // Each opens with what it does, and staff's changes.
  const special = held.getByRole("listitem", { name: "Blade of Saulot, held by Agnes" });
  await special.getByRole("button", { name: "Blade of Saulot, held by Agnes" }).click();
  await expect(special.getByText("Special, by Armoury")).toBeVisible();
  await expect(special.getByRole("list", { name: "Blade of Saulot's special effects" })).toContainText("Drinks the Blood: Once a game");
  await l.getByLabel("Held by", { exact: true }).selectOption({ label: "Agnes" });
  await l.getByLabel("Kind", { exact: true }).selectOption({ label: "Melee weapons" });
  await expect(held.getByRole("listitem", { name: /, held by / })).toHaveCount(2);
  await expect(held.getByRole("listitem", { name: "Silver Dagger, held by Agnes" })).toBeVisible();
  await expect(held.getByRole("listitem", { name: "Wooden Stake, held by Bram" })).toHaveCount(0);
  await l.screenshot(shots("troupe-equipment"));

  // The lead changes the dagger with a reason, and takes the rifle back.
  const dagger = held.getByRole("listitem", { name: "Silver Dagger, held by Agnes" });
  await dagger.getByRole("button", { name: "Silver Dagger, held by Agnes" }).click();
  await dagger.getByRole("button", { name: "Change" }).click();
  const change = dagger.getByRole("form", { name: "Change Silver Dagger" });
  await change.getByLabel("Name", { exact: true }).fill("Grandmother's dagger");
  await change.getByLabel("Why it changes").fill("An heirloom");
  await change.getByRole("button", { name: "Save changes" }).click();
  const heirloom = held.getByRole("listitem", { name: "Grandmother's dagger, held by Agnes" });
  await heirloom.getByRole("button", { name: "History" }).click();
  await expect(heirloom.getByRole("list", { name: "Grandmother's dagger's history" })).toContainText("Changed: renamed from Silver Dagger (An heirloom)");
  await l.getByLabel("Kind", { exact: true }).selectOption({ label: "Every kind" });
  const rifle = held.getByRole("listitem", { name: "Hunting rifle, held by Agnes" });
  await rifle.getByRole("button", { name: "Hunting rifle, held by Agnes" }).click();
  await rifle.getByRole("button", { name: "Take back" }).click();
  await rifle.getByLabel("Why it is taken back").fill("Lost in the river");
  await rifle.getByRole("button", { name: "Take back Hunting rifle" }).click();
  await expect(held.getByRole("listitem", { name: "Hunting rifle, held by Agnes" })).toHaveCount(0);

  await p.goto(`/characters/${agnes}/log`);
  await expect(p.getByText("equip-lead took Hunting rifle back from Agnes (equip-player): Lost in the river")).toBeVisible();
  await expect(p.getByText("equip-lead changed Agnes (equip-player)'s Silver Dagger: renamed from Silver Dagger (An heirloom).")).toBeVisible();
});

test("a player reads their character's equipment and what each quality does, on its page, its Play View and its printed sheet", async ({ browser }) => {
  const custodian = await person(browser, "kit-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "kit-lead");
  const player = await person(browser, "kit-player");
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Quartermaster ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const { id: odile } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: "Odile" });
  await send(player.page, "PUT", `/api/characters/${odile}/traits`, { category: "clan", name: "Brujah", rating: null });
  for (const [category, picks] of Object.entries({ ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Haven", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] }))
    await send(player.page, "PUT", `/api/characters/${odile}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send(player.page, "POST", `/api/characters/${odile}/creation/complete`);
  const asked = await send(player.page, "POST", `/api/characters/${odile}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);

  // Nothing given yet: the player is told where equipment comes from, on both tabs.
  const p = player.page;
  await p.goto(`/characters/${odile}`);
  await p.locator("main").getByRole("link", { name: "Equipment", exact: true }).click();
  await expect(p.getByText("No equipment yet. Your storytellers give equipment.")).toBeVisible();
  await p.goto(`/play/characters/${odile}`);
  await p.getByRole("tab", { name: "Equipment" }).click();
  await expect(p.getByText("No equipment yet. Your storytellers give equipment.")).toBeVisible();

  // The lead gives her a sports car, a flak vest and the book's Silver Dagger, with a note for staff.
  const give = (item: object) => send(lead.page, "POST", `/api/troupes/${troupe.id}/equipment`, { character_id: odile, grade: "standard", ...item });
  await give({ name: "Sports Car", kind: "miscellaneous", qualities: [{ name: "Flashy" }, { name: "Stylish" }] });
  await give({ name: "Flak Vest", kind: "protective", qualities: [{ name: "Ballistic" }, { name: "Chest Plate" }] });
  await give({ name: "Silver Dagger", kind: "melee", qualities: [{ name: "Concealable" }, { name: "Silver" }], description: "Her sire's.", staff_note: "Cursed" });

  // Her page's Equipment tab: weapons first, each quality with its effect and page, and where it came from.
  await p.goto(`/characters/${odile}/equipment`);
  const held = p.getByRole("list", { name: "Equipment" });
  await expect(held.locator(":scope > li h3")).toHaveText(["Silver Dagger", "Flak Vest", "Sports Car"]);
  const dagger = held.getByRole("listitem", { name: "Silver Dagger" });
  await expect(dagger.getByText("Melee weapon", { exact: true })).toBeVisible();
  await expect(dagger.getByText("1 hand · 1 damage · range 2 steps")).toBeVisible();
  const qualities = dagger.getByRole("list", { name: "Silver Dagger's qualities" });
  await expect(qualities).toContainText("Concealable: Can't be seen when hidden");
  await expect(qualities).toContainText("Silver: Silver-edged, plated or made: aggravated damage to werewolves");
  await expect(qualities).toContainText("MET: VTM p. 517");
  await expect(dagger.getByText("Her sire's.")).toBeVisible();
  await expect(dagger.getByText(/^Given by kit-lead of Quartermaster/)).toBeVisible();
  await expect(dagger.getByText(/Staff note/)).toHaveCount(0);
  await p.screenshot(shots("character-equipment"));

  // The lead, staff of her home troupe, sees the staff note there too.
  await lead.page.goto(`/characters/${odile}/equipment`);
  await expect(lead.page.getByRole("listitem", { name: "Silver Dagger" }).getByText("Staff note: Cursed")).toBeVisible();

  // The Play View's tab: weapons, then armour, then the rest, each quality as it plays.
  await p.goto(`/play/characters/${odile}`);
  await p.getByRole("tab", { name: "Equipment" }).click();
  await expect(p.getByRole("main").getByRole("heading", { level: 2 })).toHaveText(["Weapons", "Protective gear", "Other equipment"]);
  const card = p.getByRole("region", { name: "Weapons" }).getByRole("listitem", { name: "Silver Dagger" });
  await expect(card.getByText("Concealable: Hidden until searched")).toBeVisible();
  await expect(card.getByText("Silver: Aggravated damage to werewolves")).toBeVisible();
  await expect(p.getByRole("region", { name: "Protective gear" }).getByText("Ballistic: +3 defence against firearms, +1 against the rest")).toBeVisible();
  // The full effect: open at once on a wide screen, a tap away on a phone.
  const full = card.getByText(/Silver-edged, plated or made/);
  if (test.info().project.name === "phone") {
    await expect(full).toBeHidden();
    await card.getByRole("button", { expanded: false }).click();
  }
  await expect(full).toBeVisible();
  await expect(card.getByText("Her sire's.")).toBeVisible();
  await p.screenshot(shots("play-equipment"));

  // The printed sheet lists it, with no staff note.
  await p.goto(`/print/characters/${odile}`);
  const printed = p.getByRole("list", { name: "Equipment" });
  await expect(printed).toContainText("Silver Dagger · Melee weapon · 1 hand · 1 damage · range 2 steps");
  await expect(printed).toContainText("Concealable: Hidden until searched; Silver: Aggravated damage to werewolves");
  await expect(p.getByText("Cursed")).toHaveCount(0);
});

test("a player equips a katana and a flak vest in the Pools drawer, and the pools change by the book's amounts until they are put away", async ({ browser }) => {
  const custodian = await person(browser, "gear-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "gear-lead");
  const player = await person(browser, "gear-player");
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Gear Locker ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const { id: brunhild } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: "Brunhild" });
  await send(player.page, "PUT", `/api/characters/${brunhild}/traits`, { category: "clan", name: "Brujah", rating: null });
  for (const [category, picks] of Object.entries({ ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Haven", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] }))
    await send(player.page, "PUT", `/api/characters/${brunhild}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send(player.page, "POST", `/api/characters/${brunhild}/creation/complete`);
  const asked = await send(player.page, "POST", `/api/characters/${brunhild}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  const give = (item: object) => send(lead.page, "POST", `/api/troupes/${troupe.id}/equipment`, { character_id: brunhild, grade: "standard", ...item });
  await give({ name: "Katana", kind: "melee", qualities: [{ name: "Accurate" }, { name: "Brutal" }] });
  await give({ name: "Flak Vest", kind: "protective", qualities: [{ name: "Ballistic" }, { name: "Chest Plate" }] });
  await give({ name: "Chain Mail", kind: "protective", qualities: [{ name: "Chest Plate" }, { name: "Hardened" }] });
  await give({ name: "Pistol", kind: "ranged", qualities: [{ name: "Fast" }, { name: "Quick Draw" }] });
  await give({ name: "Bow", kind: "ranged", archaic: true, qualities: [{ name: "Accurate" }, { name: "Deadly" }] });

  const p = player.page;
  await p.goto(`/play/characters/${brunhild}?tab=pools`);
  const row = (name: RegExp) => p.getByRole("main").getByRole("listitem").filter({ hasText: name }).first();
  const totalOf = async (name: RegExp) => Number(await row(name).locator("strong").first().textContent());
  const melee = row(/^Melee attack/);
  const dodge = row(/^Dodge/);
  await expect(melee).toBeVisible();
  const [meleeBefore, dodgeBefore, initiativeBefore] = [await totalOf(/^Melee attack/), await totalOf(/^Dodge/), await totalOf(/^Initiative/)];
  const switches = p.getByRole("button", { name: "Forms, powers and modifiers" });
  await expect(switches).toHaveAccessibleDescription("Nothing in use");
  await switches.click();
  const equipment = p.getByRole("group", { name: "Equipment" });
  await expect(equipment.getByText("Accurate: +2 Melee attack, attacks with it")).toBeVisible();
  await expect(equipment.getByText("Ballistic: +3 Dodge, against firearms")).toBeVisible();

  // The Katana's Accurate adds 2 to the Melee attack, named in its breakdown.
  await p.getByLabel("Katana equipped").check();
  await expect(melee).toContainText("Katana: Accurate 2");
  await expect.poll(() => totalOf(/^Melee attack/)).toBe(meleeBefore + 2);
  // The flak vest's Ballistic: +3 against firearms and +1 against the rest, each a line under Dodge.
  await p.getByLabel("Flak Vest equipped").check();
  const firearms = dodge.getByRole("listitem").filter({ hasText: /^Against firearms/ });
  await expect(firearms).toContainText("(+3 Flak Vest: Ballistic)");
  await expect(firearms.locator("strong")).toHaveText(String(dodgeBefore + 3));
  await expect(dodge.getByRole("listitem").filter({ hasText: /^Against Brawl, Melee and thrown weapons/ }).locator("strong")).toHaveText(String(dodgeBefore + 1));
  expect(await totalOf(/^Dodge/)).toBe(dodgeBefore);
  await expect(switches).toHaveAccessibleDescription("In use: Katana, Flak Vest");
  await p.screenshot(shots("play-equipped"));

  // One piece of protective gear at a time: the chain mail takes the vest off, and says so.
  await p.getByLabel("Chain Mail equipped").check();
  await expect(equipment.getByText("Took off Flak Vest (one worn at a time).")).toBeVisible();
  await expect(p.getByLabel("Flak Vest equipped")).not.toBeChecked();
  await expect(dodge.getByRole("listitem").filter({ hasText: /^Against Brawl, Melee and thrown weapons/ })).toContainText("(+3 Chain Mail: Hardened)");
  // Two hands of weapons: the two-handed Katana is put away for the pistol, whose Fast adds 3 to initiative.
  await p.getByLabel("Pistol equipped").check();
  await expect(equipment.getByText("Put away Katana (two hands at most).")).toBeVisible();
  await expect(p.getByLabel("Katana equipped")).not.toBeChecked();
  await expect(melee).not.toContainText("Katana");
  await expect.poll(() => totalOf(/^Melee attack/)).toBe(meleeBefore);
  await expect.poll(() => totalOf(/^Initiative/)).toBe(initiativeBefore + 3);
  await expect(switches).toHaveAccessibleDescription("In use: Chain Mail, Pistol");

  // Kept: after a reload, and on the printed sheet beside the pools they change.
  await expect(p.getByRole("status")).toHaveText("Saved");
  await p.reload();
  await expect(switches).toHaveAccessibleDescription("In use: Chain Mail, Pistol");
  await p.goto(`/print/characters/${brunhild}`);
  await expect(p.getByText("+3 Chain Mail: Hardened against Brawl, Melee and thrown weapons")).toBeVisible();
  await expect(p.getByText("(+3 Pistol: Fast)")).toBeVisible();

  // An archaic bow shoots with Firearms or Athletics (p. 279): its Accurate counts on both.
  await p.goto(`/play/characters/${brunhild}?tab=pools`);
  await switches.click();
  await p.getByLabel("Bow equipped").check();
  await expect(equipment.getByText("Put away Pistol (two hands at most).")).toBeVisible();
  await expect(row(/^Firearms attack/)).toContainText("Bow: Accurate 2");
  await expect(row(/^Thrown or bow attack/)).toContainText("Bow: Accurate 2");
  await expect(melee).not.toContainText("Bow");

  // Put away, the pools are as they were.
  await p.getByLabel("Chain Mail equipped").uncheck();
  await p.getByLabel("Bow equipped").uncheck();
  await expect(switches).toHaveAccessibleDescription("Nothing in use");
  await expect(dodge.getByRole("listitem").filter({ hasText: /^Against/ })).toHaveCount(0);
  await expect.poll(() => totalOf(/^Initiative/)).toBe(initiativeBefore);
  await expect.poll(() => totalOf(/^Melee attack/)).toBe(meleeBefore);
});

test("players give equipment to each other in their home troupe and discard it, with Undo on the Play View, and staff restore it", async ({ browser }) => {
  const custodian = await person(browser, "swap-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "swap-lead");
  const player = await person(browser, "swap-player");
  const second = await person(browser, "swap-second");
  const call = (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await call(page, method, url, data);
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Pawnshop ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const ferry = await send(custodian.page, "POST", "/api/troupes", { name: `Ferry ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, ferry.id);
  const build = async (page: Page, name: string, home: string) => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    for (const [category, picks] of Object.entries({ ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Haven", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] }))
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([n, rating]) => ({ name: n, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`);
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: home });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id as string;
  };
  // Isaura and Corwin are at home in the Pawnshop; Halvard's home is the Ferry.
  const isaura = await build(player.page, "Isaura", troupe.id);
  const corwin = await build(second.page, "Corwin", troupe.id);
  const halvard = await build(second.page, "Halvard", ferry.id);
  const give = (item: object) => send(lead.page, "POST", `/api/troupes/${troupe.id}/equipment`, { character_id: isaura, grade: "standard", ...item });
  await give({ name: "Silver Dagger", kind: "melee", qualities: [{ name: "Concealable" }, { name: "Silver" }] });
  await give({ name: "Flak Vest", kind: "protective", qualities: [{ name: "Ballistic" }] });
  const holds = async (page: Page, character: string) =>
    ((await (await page.request.get(`/api/characters/${character}/equipment`)).json()).items as { name: string }[]).map((i) => i.name);

  // Isaura's player gives Corwin the Silver Dagger from her page, picking him from the home troupe's characters.
  const p = player.page;
  await p.goto(`/characters/${isaura}/equipment`);
  const card = p.getByRole("list", { name: "Equipment" }).getByRole("listitem", { name: "Silver Dagger" });
  await card.getByRole("button", { name: "Give", exact: true }).click();
  const form = card.getByRole("form", { name: "Give Silver Dagger" });
  await form.getByRole("combobox", { name: "Give it to" }).click();
  await expect(p.getByRole("listbox", { name: "Characters" }).getByRole("option")).toHaveText(["Corwinswap-secondPC"]);
  await p.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Corwin/ }).click();
  await p.screenshot(shots("equipment-give"));
  await form.getByRole("button", { name: "Give to Corwin" }).click();
  await expect(p.getByText("Gave Silver Dagger to Corwin.")).toBeVisible();
  await expect(p.getByRole("listitem", { name: "Silver Dagger" })).toHaveCount(0);

  // The API refuses giving to a character of another home troupe.
  const vest = (await (await p.request.get(`/api/characters/${isaura}/equipment`)).json()).items[0];
  const refused = await call(p, "POST", `/api/characters/${isaura}/equipment/${vest.id}/give`, { to_character_id: halvard });
  expect(refused.status()).toBe(422);
  expect((await refused.json()).detail).toContain("equipment passes only between characters of the same home troupe");

  // Corwin's player sees it on both his tabs, and was told.
  const s = second.page;
  const told = (await (await s.request.get("/api/notifications")).json()).items.map((i: { summary: string }) => i.summary);
  expect(told).toContain("swap-player gave Corwin Silver Dagger, from Isaura.");
  await s.goto(`/characters/${corwin}/equipment`);
  await expect(s.getByRole("list", { name: "Equipment" }).getByRole("listitem", { name: "Silver Dagger" })).toBeVisible();
  await s.goto(`/play/characters/${corwin}`);
  await s.getByRole("tab", { name: "Equipment" }).click();
  const weapons = s.getByRole("region", { name: "Weapons" });
  await expect(weapons.getByRole("listitem", { name: "Silver Dagger" })).toBeVisible();

  // On the Play View he gives it back, and undoes it.
  await weapons.getByRole("listitem", { name: "Silver Dagger" }).getByRole("button", { name: "Give", exact: true }).click();
  await s.getByRole("combobox", { name: "Give it to" }).fill("isa");
  await s.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Isaura/ }).click();
  await s.getByRole("button", { name: "Give to Isaura" }).click();
  await expect(s.getByRole("listitem", { name: "Silver Dagger" })).toHaveCount(0);
  const thisGame = s.getByRole("region", { name: "Given or discarded this game" });
  await expect(thisGame).toContainText("Gave Silver Dagger to Isaura");
  await expect.poll(() => holds(p, isaura)).toContain("Silver Dagger");
  await thisGame.getByRole("button", { name: "Undo Gave Silver Dagger to Isaura" }).click();
  await expect.poll(() => holds(s, corwin)).toEqual(["Silver Dagger"]);
  await expect(weapons.getByRole("listitem", { name: "Silver Dagger" })).toBeVisible();

  // Then he discards it, with a note.
  await weapons.getByRole("listitem", { name: "Silver Dagger" }).getByRole("button", { name: "Discard" }).click();
  await s.getByLabel("Where it went (optional)").fill("Lost in the river");
  await s.getByRole("button", { name: "Discard Silver Dagger" }).click();
  await expect(thisGame).toContainText("Discarded Silver Dagger");
  await expect(s.getByText("No equipment yet. Your storytellers give equipment.")).toBeVisible();
  await s.screenshot(shots("play-equipment-discarded"));
  await expect.poll(() => holds(s, corwin)).toEqual([]);

  // The troupe's Equipment tab says a discarded item isn't shown; the lead shows it, with the note and its history, and restores it.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}`);
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: "Equipment", exact: true }).click();
  const found = l.getByRole("list", { name: "Equipment", exact: true });
  await expect(found.getByRole("listitem", { name: "Silver Dagger, held by Corwin" })).toHaveCount(0);
  await l.getByRole("button", { name: "Show it" }).click();
  const kept = found.getByRole("listitem", { name: "Silver Dagger, held by Corwin" });
  await expect(kept.getByText("Discarded", { exact: true })).toBeVisible();
  await kept.getByRole("button", { name: "Silver Dagger, held by Corwin" }).click();
  await expect(kept.getByText(/^Discarded by swap-second, .*: Lost in the river$/)).toBeVisible();
  await kept.getByRole("button", { name: "History" }).click();
  const history = kept.getByRole("list", { name: "Silver Dagger's history" });
  await expect(history).toContainText("Given by Isaura to Corwin");
  await expect(history).toContainText("Back from Isaura to Corwin (undone in the Play View)");
  await expect(history).toContainText("Discarded by Corwin (Lost in the river)");
  await l.screenshot(shots("troupe-equipment-discarded"));
  await kept.getByRole("button", { name: "Restore to Corwin" }).click();
  await expect(kept.getByText("Discarded", { exact: true })).toHaveCount(0);
  await expect(kept.getByRole("button", { name: "Change" })).toBeVisible();
  expect(await holds(s, corwin)).toEqual(["Silver Dagger"]);
});

test("a storyteller gives the Book of Nod from a character's page, its player passes it on, and the history shows both", async ({ browser }) => {
  const custodian = await person(browser, "scribe-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "scribe-lead");
  const player = await person(browser, "scribe-player");
  const second = await person(browser, "scribe-second");
  const call = (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await call(page, method, url, data);
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Scriptorium ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = async (page: Page, name: string) => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    for (const [category, picks] of Object.entries({ ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Haven", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] }))
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([n, rating]) => ({ name: n, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`);
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id as string;
  };
  const theodora = await build(player.page, "Theodora");
  const lucan = await build(second.page, "Lucan");

  // No sheet offers a text: it isn't a trait.
  const rules = await (await player.page.request.get("/api/rules/vampire")).json();
  expect(rules.categories.map((c: { key: string }) => c.key)).not.toContain("vampiric_texts");

  // The lead gives Theodora the Book of Nod from her page: the book's text, with its line and pages, and no qualities.
  const l = lead.page;
  await l.goto(`/characters/${theodora}`);
  await l.getByRole("button", { name: "Give equipment" }).click();
  const form = l.getByRole("dialog").getByRole("form", { name: "Give equipment" });
  await form.getByLabel("Start from").selectOption({ label: "The Book of Nod" });
  await expect(form.getByLabel("Kind")).toHaveValue("text");
  await expect(form.getByLabel("Description (optional)")).toHaveValue(/legends of Caine/);
  await expect(form.getByText("The Book of Nod: MET: VTM pp. 28, 421 & 453")).toBeVisible();
  await expect(form.getByLabel("What it is")).toHaveText("A vampiric text: it has no qualities, and isn't equipped at a game.");
  await expect(form.getByLabel("Add a quality")).toHaveCount(0);
  await form.getByRole("button", { name: "Give to Theodora" }).click();
  await expect(l.getByText("Gave Theodora The Book of Nod.")).toBeVisible();

  // Its player sees it, and can't give one to herself.
  const p = player.page;
  const mine = await call(p, "POST", `/api/troupes/${troupe.id}/equipment`, { character_id: theodora, name: "The Book of Nod", kind: "text", grade: "standard", qualities: [] });
  expect(mine.status()).toBe(403);
  await p.goto(`/characters/${theodora}/equipment`);
  const card = p.getByRole("list", { name: "Equipment" }).getByRole("listitem", { name: "The Book of Nod" });
  await expect(card).toContainText("Vampiric text");
  await expect(card).toContainText("legends of Caine");

  // She passes it to Lucan.
  await card.getByRole("button", { name: "Give", exact: true }).click();
  await card.getByRole("form", { name: "Give The Book of Nod" }).getByRole("combobox", { name: "Give it to" }).click();
  await p.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Lucan/ }).click();
  await card.getByRole("button", { name: "Give to Lucan" }).click();
  await expect(p.getByText("Gave The Book of Nod to Lucan.")).toBeVisible();
  await expect(p.getByRole("listitem", { name: "The Book of Nod" })).toHaveCount(0);

  // Lucan's player has it on his Play View, with the texts, never equipped.
  const s = second.page;
  await s.goto(`/play/characters/${lucan}`);
  await s.getByRole("tab", { name: "Equipment" }).click();
  await expect(s.getByRole("region", { name: "Vampiric texts" }).getByRole("listitem", { name: "The Book of Nod" })).toBeVisible();
  await s.screenshot(shots("play-vampiric-text"));

  // The troupe's Equipment tab finds it by its kind, and its history shows both.
  await l.goto(`/troupes/${troupe.id}`);
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: "Equipment", exact: true }).click();
  await l.getByLabel("Kind", { exact: true }).selectOption({ label: "Vampiric texts" });
  const held = l.getByRole("list", { name: "Equipment", exact: true });
  const nod = held.getByRole("listitem", { name: "The Book of Nod, held by Lucan" });
  await nod.getByRole("button", { name: "The Book of Nod, held by Lucan" }).click();
  await nod.getByRole("button", { name: "History" }).click();
  const history = nod.getByRole("list", { name: "The Book of Nod's history" });
  await expect(history).toContainText(`Given to Theodora by Scriptorium ${run}, from the template The Book of Nod`);
  await expect(history).toContainText("Given by Theodora to Lucan");
});

test("staff find who holds what in the Characters filter, and items on the Equipment tab, each view linking to the other", async ({ browser }) => {
  const custodian = await person(browser, "seek-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "seek-lead");
  const player = await person(browser, "seek-player");
  const call = (page: Page, method: "GET" | "POST" | "PUT", url: string, data?: object) => page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await call(page, method, url, data);
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupeName = `Lantern Watch ${run}`;
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);

  // Ilse (Camarilla) is the player's, at home in the troupe; Otto (Camarilla), Pell (no sect) and Rhea (Camarilla) are its NPCs.
  const { id: ilse } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: "Ilse" });
  await send(player.page, "PUT", `/api/characters/${ilse}/traits`, { category: "clan", name: "Brujah", rating: null });
  await send(player.page, "PUT", `/api/characters/${ilse}/traits`, { category: "sect", name: "Camarilla", rating: null });
  for (const [category, picks] of Object.entries({ ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Haven", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] }))
    await send(player.page, "PUT", `/api/characters/${ilse}/creation/categories/${category}`, { picks: picks.map(([n, rating]) => ({ name: n, rating })) });
  await send(player.page, "POST", `/api/characters/${ilse}/creation/complete`);
  const asked = await send(player.page, "POST", `/api/characters/${ilse}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  const npc = async (name: string, sect?: string) => {
    const { id } = await send(lead.page, "POST", `/api/troupes/${troupe.id}/npcs`, { name, wizard: false });
    if (sect) await send(lead.page, "PUT", `/api/characters/${id}/npc/ratings`, { category: "sect", name: sect, rating: null, detail: "" });
    return id as string;
  };
  const otto = await npc("Otto", "Camarilla");
  const pell = await npc("Pell");
  const rhea = await npc("Rhea", "Camarilla");
  const give = (character: string, item: object) => send(lead.page, "POST", `/api/troupes/${troupe.id}/equipment`, { character_id: character, grade: "standard", ...item });
  const stake = { name: "Wooden Stake", kind: "melee", qualities: [{ name: "Concealable" }, { name: "Staking" }] };
  const vest = { name: "Flak Vest", kind: "protective", qualities: [{ name: "Ballistic" }] };
  await give(ilse, stake);
  await give(ilse, vest);
  await give(otto, { name: "Silver Dagger", kind: "melee", qualities: [{ name: "Concealable" }, { name: "Silver" }] });
  await give(otto, vest);
  await give(pell, stake);
  const revolver = await give(pell, { name: "Old revolver", kind: "ranged", qualities: [] });
  await send(lead.page, "POST", `/api/characters/${pell}/equipment/${revolver.id}/discard`, { note: "Thrown in the canal" });
  await give(rhea, {
    name: "Lantern of Ashes",
    kind: "miscellaneous",
    grade: "special",
    qualities: [{ name: "Sturdy" }],
    effects: [{ name: "Unveiling", effect: "Its light shows anyone hidden by Obfuscate." }],
  });

  // Camarilla characters holding a staking item: only Ilse, with her stake shown.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/characters`);
  await expect(l.getByText("4 of 4 characters")).toBeVisible();
  await l.getByRole("button", { name: "Filter" }).click();
  await l.getByRole("button", { name: "+ Condition", exact: true }).click();
  const sect = l.getByRole("group", { name: "Condition" }).nth(1);
  await sect.getByLabel("What").selectOption({ label: "Clan, sect, focus…" });
  await sect.getByLabel("Category").selectOption({ label: "Sect" });
  await sect.getByLabel("Value").selectOption("Camarilla");
  await expect(l.getByText("3 of 4 characters")).toBeVisible();
  await l.getByRole("button", { name: "+ Condition", exact: true }).click();
  const staking = l.getByRole("group", { name: "Condition" }).nth(2);
  await staking.getByLabel("What").selectOption({ label: "Equipment" });
  await staking.getByLabel("Kind of item").selectOption({ label: "melee weapon" });
  await staking.getByLabel("Quality").selectOption("Staking");
  await expect(l.getByText("1 of 4 characters")).toBeVisible();
  await expect(l.getByText("Has a melee weapon with Staking")).toBeVisible();
  const rows = l.locator("main ul.divide-y > li");
  await expect(rows).toHaveCount(1);
  await expect(rows.filter({ hasText: "Ilse" }).getByText("Wooden Stake", { exact: true })).toBeVisible();
  await l.screenshot(shots("filter-equipment"));

  // Show their equipment opens the Equipment tab on Ilse's items.
  await l.getByRole("link", { name: "Show their equipment" }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupe.id}/equipment\\?holders=${ilse}$`));
  await expect(l.getByRole("list", { name: "Holders searched" })).toHaveText(/Ilse/);
  const found = l.getByRole("list", { name: "Equipment", exact: true });
  await expect(found.getByRole("listitem", { name: /, held by / })).toHaveCount(2);
  await expect(found.getByRole("listitem", { name: "Flak Vest, held by Ilse" })).toBeVisible();

  // Those with no protective gear: Pell and Rhea, with what they do hold.
  await l.goto(`/troupes/${troupe.id}/characters`);
  await l.getByRole("button", { name: "Filter" }).click();
  await l.getByRole("button", { name: "+ Condition", exact: true }).click();
  const armour = l.getByRole("group", { name: "Condition" }).nth(1);
  await armour.getByLabel("What").selectOption({ label: "Equipment" });
  await armour.getByLabel("How").selectOption({ label: "does not hold" });
  await armour.getByLabel("Kind of item").selectOption({ label: "protective gear" });
  await expect(l.getByText("2 of 4 characters")).toBeVisible();
  await expect(rows.filter({ hasText: "Pell" }).getByText("Wooden Stake", { exact: true })).toBeVisible();
  await expect(rows.filter({ hasText: "Rhea" }).getByText("Lantern of Ashes", { exact: true })).toBeVisible();

  // On the Equipment tab, a word in a special effect finds the lantern.
  await l.goto(`/troupes/${troupe.id}/equipment`);
  await expect(found.getByRole("listitem", { name: /, held by / })).toHaveCount(6);
  await l.getByLabel("Search equipment").fill("obfuscate");
  await expect(l.getByText("1 item", { exact: true })).toBeVisible();
  const lantern = found.getByRole("listitem", { name: "Lantern of Ashes, held by Rhea" });
  await lantern.getByRole("button", { name: "Lantern of Ashes, held by Rhea" }).click();
  await expect(lantern.getByRole("list", { name: "Lantern of Ashes's special effects" })).toContainText("Unveiling: Its light shows anyone hidden by Obfuscate.");

  // The discarded revolver shows with Discarded ticked, and its history says where it went.
  await l.getByLabel("Search equipment").fill("revolver");
  await expect(l.getByText("No equipment matches.")).toBeVisible();
  await expect(l.getByText("1 discarded not shown")).toBeVisible();
  await l.getByLabel("Discarded", { exact: true }).click();
  await expect(l.getByLabel("Discarded", { exact: true })).toBeChecked();
  const gone = found.getByRole("listitem", { name: "Old revolver, held by Pell" });
  await expect(gone.getByText("Discarded", { exact: true })).toBeVisible();
  await gone.getByRole("button", { name: "Old revolver, held by Pell" }).click();
  await gone.getByRole("button", { name: "History" }).click();
  const history = gone.getByRole("list", { name: "Old revolver's history" });
  await expect(history).toContainText(`Given to Pell by ${troupeName}`);
  await expect(history).toContainText("Discarded by Pell (Thrown in the canal)");
  await l.screenshot(shots("troupe-equipment-search"));

  // Melee weapons, held or discarded, export as a CSV.
  await l.getByLabel("Search equipment").fill("");
  await l.getByLabel("Kind", { exact: true }).selectOption({ label: "Melee weapons" });
  await expect(found.getByRole("listitem", { name: /, held by / })).toHaveCount(3);
  const downloading = l.waitForEvent("download");
  await l.getByRole("button", { name: "Export CSV" }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toBe(`${troupeName} equipment.csv`);
  const { readFile } = await import("node:fs/promises");
  const csv = (await readFile(await download.path(), "utf8")).trimEnd().split("\r\n");
  expect(csv[0]).toBe("Item,Held by,Player,Kind,Grade,Qualities,Special effects,Description,Status,Given by,Troupe,Given on,Staff note");
  expect(csv.slice(1).map((line) => line.split(",").slice(0, 3).join(","))).toEqual(["Wooden Stake,Ilse,seek-player", "Silver Dagger,Otto,NPC", "Wooden Stake,Pell,NPC"]);

  // Find these characters opens the Characters list on their holders.
  await l.getByRole("link", { name: "Find these characters" }).click();
  await expect(l.getByText("3 of 4 characters")).toBeVisible();
  await expect(l.getByText("Character is Ilse, Otto or Pell")).toBeVisible();

  // A player is refused both searches by the API.
  const p = player.page;
  expect((await call(p, "GET", `/api/troupes/${troupe.id}/equipment?q=stake`)).status()).toBe(403);
  const searched = await call(p, "POST", `/api/troupes/${troupe.id}/characters/search`, { match: "all", items: [{ what: "equipment", op: "has", value: { quality: "Staking" } }] });
  expect(searched.status()).toBe(403);
});
