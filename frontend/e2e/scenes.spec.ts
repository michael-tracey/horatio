import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, openScene } from "./support";

/** Scenes: storytellers pinning NPCs and tapping for them. */

closeContextsAfterEach();

test("a storyteller pins three NPCs in a Scene view, taps for two, and each full Play View agrees", async ({ browser }) => {
  const custodian = await person(browser, "scene-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "scene-lead");
  const troupeName = `Court of Masks ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Three NPCs, made straight through the API.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const npcs: Record<string, string> = {};
  for (const name of ["Alder", "Brant", "Cassia"]) {
    const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(made.status(), await made.text()).toBe(201);
    npcs[name] = (await made.json()).id;
  }
  const state = async (name: string) => (await p.request.get(`/api/characters/${npcs[name]}/play`)).json();

  // From the At game tab, through the troupe's scenes, to a new empty one.
  await p.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await p.getByRole("link", { name: "At game" }).click();
  await p.getByRole("link", { name: "Open the scenes" }).click();
  await expect(p.getByRole("heading", { name: "Scenes", exact: true })).toBeVisible();
  await p.getByLabel("Name of a new scene").fill("Masked ball");
  await p.getByRole("button", { name: "New scene" }).click();
  await expect(p.getByRole("heading", { name: "Masked ball", exact: true })).toBeVisible();
  await expect(p.getByText("Nobody is in the scene yet.")).toBeVisible();
  const sceneUrl = new URL(p.url()).pathname;
  const pinned = async () => (await (await p.request.get(`/api/troupes/${troupeId}/scenes/${sceneUrl.split("/").pop()}`)).json()).characters.length;

  // Pinned by searching: typing narrows the list, and a pinned one is not offered again.
  const search = p.getByRole("combobox", { name: "Add to the scene" });
  await search.fill("al");
  await expect(p.getByRole("option")).toHaveCount(1);
  await p.getByRole("option", { name: /Alder/ }).click();
  await search.fill("bra");
  await p.getByRole("option", { name: /Brant/ }).click();
  await search.click();
  await expect(p.getByRole("option", { name: /Alder/ })).toHaveCount(0);
  await p.getByRole("option", { name: /Cassia/ }).click();
  const card = (name: string) => p.getByRole("article", { name });
  await expect(p.getByRole("article")).toHaveCount(3);
  await expect(card("Cassia").getByLabel("Blood: 10 of 10")).toBeVisible();

  // The scene is kept on the server.
  await expect.poll(pinned).toBe(3);
  await p.reload();
  await expect(p.getByRole("article")).toHaveCount(3);
  await expect(card("Brant")).toBeVisible();

  // Taps for two of them: Blood and Health.
  const alder = card("Alder");
  await alder.getByRole("button", { name: "Spend Blood", exact: true }).click();
  await alder.getByRole("button", { name: "Spend Blood", exact: true }).click();
  await alder.getByRole("button", { name: "+ Normal" }).click();
  await expect(alder.getByLabel("Blood: 8 of 10")).toBeVisible();
  await expect(alder.getByLabel(/^Health: 1 of \d+ marked$/)).toBeVisible();
  const brant = card("Brant");
  await brant.getByRole("button", { name: "Spend Blood", exact: true }).click();
  await brant.getByRole("button", { name: "+ Aggravated" }).click();
  await expect(brant.getByLabel("Blood: 9 of 10")).toBeVisible();
  await expect(alder.getByRole("status")).toHaveText("Saved");
  await expect(brant.getByRole("status")).toHaveText("Saved");
  await expect(card("Cassia").getByLabel("Blood: 10 of 10")).toBeVisible();
  await p.screenshot(shots("scene"));

  // The server has the taps, and the full Play View of each shows the same.
  await expect.poll(async () => (await state("Alder")).blood.value).toBe(8);
  expect((await state("Alder")).health.marks).toEqual(["normal"]);
  expect((await state("Brant")).health.marks).toEqual(["aggravated"]);
  expect((await state("Cassia")).log).toHaveLength(0);
  await alder.getByRole("link", { name: "Open the full Play View of Alder" }).click();
  await expect(p.getByLabel("Blood: 8 of 10")).toBeVisible();
  await expect(p.getByLabel("normal damage")).toHaveCount(1);
  await expect(p.getByText("Blood 10 → 9")).toBeVisible();
  // Opened from the scene, the way back is to the scene, whichever tab is looked up.
  await expect(p.getByRole("link", { name: "← Alder" })).toHaveCount(0);
  await p.getByRole("tab", { name: "Sheet" }).click();
  await p.getByRole("link", { name: "← Back to the scene" }).click();
  await expect(p.getByRole("heading", { name: "Masked ball", exact: true })).toBeVisible();
  await expect(p.getByRole("article")).toHaveCount(3);
  await p.goto(`/play/characters/${npcs.Brant}`);
  await expect(p.getByRole("link", { name: "← Brant" })).toBeVisible();
  await expect(p.getByLabel("Blood: 9 of 10")).toBeVisible();
  await expect(p.getByLabel("aggravated damage")).toHaveCount(1);
  await expect(p.getByLabel("normal damage")).toHaveCount(0);
  // A tap on the full Play View is on the card, and Undo on the card takes back the newest tap.
  const before = (await state("Cassia")).willpower;
  await p.goto(`/play/characters/${npcs.Cassia}`);
  await p.getByLabel("Quick notes").uncheck();
  await p.getByRole("button", { name: "Spend Willpower", exact: true }).last().click();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await p.goto(sceneUrl);
  const cassia = card("Cassia");
  await expect(cassia.getByLabel(`Willpower: ${before.value - 1} of ${before.most}`)).toBeVisible();
  await cassia.getByRole("button", { name: /^Undo Willpower/ }).click();
  await expect(cassia.getByLabel(`Willpower: ${before.value} of ${before.most}`)).toBeVisible();
  await expect(cassia.getByRole("status")).toHaveText("Saved");
  await expect.poll(async () => (await state("Cassia")).willpower.value).toBe(before.value);
  await cassia.getByRole("button", { name: /^Log/ }).click();
  await expect(cassia.getByText(/^Undid: Willpower/)).toBeVisible();

  // Reset on a card puts that character back, and only that one.
  await brant.getByRole("button", { name: /^Reset/ }).click();
  await brant.getByRole("button", { name: "Reset for next game…" }).click();
  await brant.getByRole("button", { name: "Reset for next game", exact: true }).click();
  await expect(brant.getByLabel("Blood: 10 of 10")).toBeVisible();
  await expect(brant.getByLabel(/^Health: 0 of \d+ marked$/)).toBeVisible();
  await expect(alder.getByLabel("Blood: 8 of 10")).toBeVisible();

  // Removing one takes it off the scene, not out of the troupe.
  await cassia.getByRole("button", { name: "Remove Cassia from the scene" }).click();
  await expect(p.getByRole("article")).toHaveCount(2);
  await expect.poll(pinned).toBe(2);
  await p.reload();
  await expect(p.getByRole("article")).toHaveCount(2);
  await expect(card("Cassia")).toHaveCount(0);
  await search.click();
  await expect(p.getByRole("option", { name: /Cassia/ })).toBeVisible();
  await expect.poll(async () => (await state("Alder")).blood.value).toBe(8);
});

test("a Scene card shows an NPC's best attacks and defences, and its Pools and Powers sections follow a form", async ({ browser }) => {
  const custodian = await person(browser, "pools-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "pools-lead");
  const troupeName = `Court of Hounds ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC with four attacks and Shape of the Beast: Physical 5, Brawl 3, Melee 2, Firearms 1, Athletics 1, Dodge 2.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Vesper", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  for (const [category, name, rating] of [
    ["clan", "Gangrel", null],
    ["attributes", "Physical", 5],
    ["attributes", "Mental", 3],
    ["skills", "Brawl", 3],
    ["skills", "Melee", 2],
    ["skills", "Firearms", 1],
    ["skills", "Athletics", 1],
    ["skills", "Dodge", 2],
    ["disciplines", "Protean", 4],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category, name, rating, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
  }
  await p.goto(`/characters/${npc}/sheet`);
  const choices = p.getByLabel("Shape of the Beast choices");
  await choices.getByRole("button", { name: "choose" }).click();
  await choices.getByLabel("Fight form", { exact: true }).fill("bear");
  await choices.getByLabel("Fight form template").selectOption("Huge");
  await choices.getByRole("button", { name: "Save" }).click();
  await expect(choices).toContainText("fight form bear · fight form template Huge");

  // Pinned: the top three attacks (Thrown, the fourth, is left out) and the defences are on the card.
  await openScene(p, troupeId, "Vesper's hunt");
  await p.getByRole("combobox", { name: "Add to the scene" }).fill("Vesper");
  await p.getByRole("option", { name: /Vesper/ }).click();
  const card = p.getByRole("article", { name: "Vesper" });
  await expect(card).toContainText("Attack Unarmed 8 (1 dmg) · Melee 7");
  await expect(card).toContainText("Firearms 6");
  await expect(card).not.toContainText("Thrown");
  await expect(card).toContainText("Defence Dodge 7");

  // A form in Powers raises the attack and shows as a badge; Undo takes it back.
  await card.getByRole("button", { name: /^Powers/ }).click();
  await card.getByLabel("Shape of the Beast: fight form (bear, Huge) on").check();
  await expect(card).toContainText("Attack Unarmed 10");
  await expect(card.getByText("Shape of the Beast: fight form (bear, Huge)", { exact: true }).first()).toBeVisible();
  await expect(card.getByRole("status")).toHaveText("Saved");
  await card.getByRole("button", { name: /^Undo Turned into Shape of the Beast/ }).click();
  await expect(card).toContainText("Attack Unarmed 8 (1 dmg)");
  await expect(card.getByLabel("Shape of the Beast: fight form (bear, Huge) on")).not.toBeChecked();

  // Pools lists every pool, Combat and Defence first, and stays open over a reload.
  await card.getByRole("button", { name: /^Pools/ }).click();
  await expect(card.getByRole("region", { name: "Combat" })).toContainText("Thrown or bow attack");
  await expect(card.getByRole("region", { name: "Defence" })).toContainText("Resisting Social powers");
  await p.reload();
  await expect(card.getByRole("region", { name: "Combat" })).toBeVisible();
  await expect(card.getByRole("button", { name: /^Powers/ })).toHaveAttribute("aria-expanded", "true");
});

test("two storytellers share a troupe's named scenes: each pins, taps and sees the other's, and the maker renames and removes", async ({ browser }) => {
  test.slow();
  const custodian = await person(browser, "named-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "named-lead");
  const second = await person(browser, "named-storyteller");
  const troupeName = `Court of Tapers ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // A second storyteller and three NPCs, made straight through the API.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const staffed = await p.request.put(`/api/troupes/${troupeId}/staff`, { headers, data: { handle: second.handle, role: "storyteller" } });
  expect(staffed.status(), await staffed.text()).toBe(200);
  const npcs: Record<string, string> = {};
  for (const name of ["Kasimir", "Lorcan", "Odile"]) {
    const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(made.status(), await made.text()).toBe(201);
    npcs[name] = (await made.json()).id;
  }
  const stocked = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Grimsby", npc_form: "stock", stock: { rating: 2 } } });
  expect(stocked.status(), await stocked.text()).toBe(201);

  // The lead's browser still has a scene of its own from before; the old address goes to the list, which offers to save it.
  await p.evaluate(([troupe, odile]) => localStorage.setItem(`horatio.scene.${troupe}`, JSON.stringify([odile])), [troupeId, npcs.Odile!]);
  await p.goto(`/play/troupes/${troupeId}/scene`);
  await expect(p).toHaveURL(new RegExp(`/play/troupes/${troupeId}/scenes$`));
  const offer = p.getByRole("region", { name: "This device's scene" });
  await expect(offer).toContainText("1 character");
  await offer.getByLabel("Name of the scene").fill("Old haunt");
  await offer.getByRole("button", { name: "Save this device's scene" }).click();
  await expect(offer).toHaveCount(0);
  await expect(p.getByRole("listitem", { name: "Old haunt" })).toContainText("Yours · 1 character");
  expect(await p.evaluate((troupe) => localStorage.getItem(`horatio.scene.${troupe}`), troupeId)).toBeNull();
  await p.reload();
  await expect(p.getByRole("listitem", { name: "Old haunt" })).toBeVisible();
  await expect(offer).toHaveCount(0);

  // Two named scenes, with a different NPC in each.
  const search = (page: Page) => page.getByRole("combobox", { name: "Add to the scene" });
  const scenes: Record<string, string> = {};
  for (const [name, npc] of [
    ["Elysium, ballroom", "Lorcan"],
    ["Warehouse ambush", "Kasimir"],
  ] as const) {
    await p.goto(`/play/troupes/${troupeId}/scenes`);
    await p.getByLabel("Name of a new scene").fill(name);
    await p.getByRole("button", { name: "New scene" }).click();
    await expect(p.getByRole("heading", { name, exact: true })).toBeVisible();
    scenes[name] = new URL(p.url()).pathname;
    await search(p).fill(npc);
    await p.getByRole("option", { name: new RegExp(npc) }).click();
    await expect(p.getByRole("article", { name: npc })).toBeVisible();
  }
  await expect(p.getByRole("article")).toHaveCount(1);
  // A Stock NPC's card is the Stock one: its kind, rating and Blood.
  await p.goto(scenes["Elysium, ballroom"]!);
  await search(p).fill("Grimsby");
  await p.getByRole("option", { name: /Grimsby/ }).click();
  await expect(p.getByRole("article", { name: "Grimsby" })).toContainText("Stock NPC · Vampire · rating 2");
  await expect(p.getByRole("article", { name: "Grimsby" }).getByLabel("Blood: 10 of 10")).toBeVisible();
  await p.goto(scenes["Warehouse ambush"]!);

  // The second storyteller has none of their own, and sees all three under All, with who made them.
  const s = second.page;
  await s.goto(`/play/troupes/${troupeId}/scenes`);
  await expect(s.getByText("You have no scenes in this troupe yet.")).toBeVisible();
  await s.getByRole("button", { name: "All" }).click();
  await expect(s.getByRole("listitem")).toHaveCount(3);
  const ambush = s.getByRole("listitem", { name: "Warehouse ambush" });
  await expect(ambush).toContainText("By named-lead · 1 character");
  // Not theirs to change.
  await expect(ambush.getByRole("button", { name: "Rename Warehouse ambush" })).toHaveCount(0);

  // They open the ambush, tap for Kasimir and pin Odile there too.
  await ambush.getByRole("link", { name: "Warehouse ambush" }).click();
  await expect(s.getByRole("heading", { name: "Warehouse ambush", exact: true })).toBeVisible();
  await expect(s.getByText("named-lead's scene")).toBeVisible();
  await expect(s.getByRole("button", { name: "Rename" })).toHaveCount(0);
  const kasimir = s.getByRole("article", { name: "Kasimir" });
  await kasimir.getByRole("button", { name: "Spend Blood", exact: true }).click();
  await expect(kasimir.getByLabel("Blood: 9 of 10")).toBeVisible();
  await expect(kasimir.getByRole("status")).toHaveText("Saved");
  await search(s).fill("Odile");
  await s.getByRole("option", { name: /Odile/ }).click();
  await expect(s.getByRole("article")).toHaveCount(2);

  // The lead, with the ambush open, sees the tap and the pin on the next refresh.
  await expect(p.getByRole("article", { name: "Kasimir" }).getByLabel("Blood: 9 of 10")).toBeVisible({ timeout: 25_000 });
  await expect(p.getByRole("article", { name: "Odile" })).toBeVisible({ timeout: 25_000 });
  await p.screenshot(shots("named-scene"));

  // Full view from a card goes back to that scene.
  await p.getByRole("link", { name: "Open the full Play View of Kasimir" }).click();
  await expect(p.getByLabel("Blood: 9 of 10")).toBeVisible();
  await p.getByRole("link", { name: "← Back to the scene" }).click();
  await expect(p).toHaveURL(new RegExp(`${scenes["Warehouse ambush"]}$`));
  await expect(p.getByRole("heading", { name: "Warehouse ambush", exact: true })).toBeVisible();

  // The maker renames one in its heading and removes the other from the list, after asking.
  await p.goto(scenes["Elysium, ballroom"]!);
  await p.getByRole("button", { name: "Rename" }).click();
  await p.getByLabel("Name of the scene").fill("Elysium, gallery");
  await p.getByRole("button", { name: "Save", exact: true }).click();
  await expect(p.getByRole("heading", { name: "Elysium, gallery", exact: true })).toBeVisible();
  await p.getByRole("link", { name: /^← Scenes/ }).click();
  const doomed = p.getByRole("listitem", { name: "Warehouse ambush" });
  await doomed.getByRole("button", { name: "Remove Warehouse ambush" }).click();
  await doomed.getByRole("button", { name: "Remove the scene" }).click();
  await expect(doomed).toHaveCount(0);
  await expect(p.getByRole("listitem", { name: "Elysium, gallery" })).toContainText("2 characters");

  // The second storyteller's list follows; removing the scene left Kasimir as he was.
  await s.goto(`/play/troupes/${troupeId}/scenes`);
  await s.getByRole("button", { name: "All" }).click();
  await expect(s.getByRole("listitem", { name: "Elysium, gallery" })).toBeVisible();
  await expect(s.getByRole("listitem", { name: "Warehouse ambush" })).toHaveCount(0);
  expect((await (await s.request.get(`/api/characters/${npcs.Kasimir}/play`)).json()).blood.value).toBe(9);
  const log = (await (await p.request.get(`/api/troupes/${troupeId}/log`)).json()) as { message: string }[];
  expect(log.map((e) => e.message)).toEqual(
    expect.arrayContaining(["named-lead removed the scene Warehouse ambush.", "named-lead renamed the scene Elysium, ballroom to Elysium, gallery."]),
  );
});

test("a Stock werewolf in a scene: Rage and health tapped on its card and undone, and its Stock Play View from Full view", async ({ browser }) => {
  const custodian = await person(browser, "stockplay-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "stockplay-lead");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Howls ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  const p = lead.page;
  const wolf = await p.request.post(`/api/troupes/${troupeId}/npcs`, {
    headers,
    data: { name: "Snarls-at-Dusk", npc_kind: "werewolf", npc_form: "stock", stock: { rating: 3, specializations: [{ type: "skill", name: "Brawl" }] } },
  });
  expect(wolf.status(), await wolf.text()).toBe(201);

  // A named scene with the werewolf pinned: its card has the stat block at a glance, Rage in Blood's place, and twice its rating in health.
  await p.goto(`/play/troupes/${troupeId}/scenes`);
  await p.getByLabel("Name of a new scene").fill("Pit fight");
  await p.getByRole("button", { name: "New scene" }).click();
  await expect(p.getByRole("heading", { name: "Pit fight", exact: true })).toBeVisible();
  const scene = new URL(p.url()).pathname;
  await p.getByRole("combobox", { name: "Add to the scene" }).fill("Snarls");
  await p.getByRole("option", { name: /Snarls-at-Dusk/ }).click();
  const card = p.getByRole("article", { name: "Snarls-at-Dusk" });
  await expect(card).toContainText("Stock NPC · Werewolf · rating 3");
  await expect(card).toContainText("Test pool 6 in most challenges");
  await expect(card).toContainText("Brawl 11");
  await expect(card.getByLabel("Rage: 10 of 10")).toBeVisible();
  await expect(card.getByLabel("Health: 0 of 6 marked")).toBeVisible();

  // Rage spent and a wound marked, then the wound undone; the log has them all.
  await card.getByRole("button", { name: "Spend Rage", exact: true }).click();
  await card.getByRole("button", { name: "Spend Rage", exact: true }).click();
  await expect(card.getByLabel("Rage: 8 of 10")).toBeVisible();
  await card.getByRole("button", { name: "+ Aggravated" }).click();
  await expect(card.getByLabel("Health: 1 of 6 marked")).toBeVisible();
  await expect(card.getByRole("status")).toHaveText("Saved");
  await card.getByRole("button", { name: /^Undo Health/ }).click();
  await expect(card.getByLabel("Health: 0 of 6 marked")).toBeVisible();
  await card.getByRole("button", { name: "+ Normal" }).click();
  await expect(card.getByLabel("Health: 1 of 6 marked")).toBeVisible();
  await expect(card.getByRole("status")).toHaveText("Saved");
  await card.getByRole("button", { name: /^Log/ }).click();
  await expect(card).toContainText("Undid: Health: took 1 aggravated");
  await expect(card).toContainText("Rage 9 → 8");
  await p.screenshot(shots("stock-scene-card"));

  // Full view is the Stock Play View: the same Rage and health, the stat block and the werewolf's rules card, and no Willpower.
  await card.getByRole("link", { name: "Open the full Play View of Snarls-at-Dusk" }).click();
  await expect(p.getByRole("heading", { name: "Snarls-at-Dusk" })).toBeVisible();
  await expect(p.getByText("Stock NPC · Werewolf · rating 3")).toBeVisible();
  await expect(p.getByLabel("Rage: 8 of 10")).toBeVisible();
  await expect(p.getByLabel("normal damage")).toHaveCount(1);
  await expect(p.getByLabel("unmarked")).toHaveCount(5);
  const block = p.getByRole("list", { name: "Stat block" });
  await expect(block.getByText("Test pool 6 in most challenges")).toBeVisible();
  await expect(block.getByText("Brawl 11")).toBeVisible();
  await expect(block.getByText("Rage 10, up to 3 a turn, regains 1 every five turns")).toBeVisible();
  await expect(block.getByText("No Willpower: no retests unless it overbids")).toBeVisible();
  await expect(p.getByRole("heading", { name: "Werewolf rules card" })).toBeVisible();
  await expect(p.getByRole("tab", { name: "Tracker" })).toHaveCount(0);
  await expect(p.getByLabel(/^Willpower/)).toHaveCount(0);
  // Spent here, it is spent on the card too.
  await p.getByRole("button", { name: "Spend Rage", exact: true }).last().click();
  await expect(p.getByLabel("Rage: 7 of 10")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await expect(p.getByText("Rage 8 → 7")).toBeVisible();
  await p.screenshot(shots("stock-play"));

  await p.getByRole("link", { name: "← Back to the scene" }).click();
  await expect(p).toHaveURL(new RegExp(`${scene}$`));
  await expect(p.getByRole("article", { name: "Snarls-at-Dusk" }).getByLabel("Rage: 7 of 10")).toBeVisible();
});
