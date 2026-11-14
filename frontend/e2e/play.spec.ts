import { expect, test, type Page } from "@playwright/test";
import { ATTRIBUTES_AND_FOCUSES, backstoryOptional, builtVampire, characterTab, closeContextsAfterEach, makeCustodian, openNewTroupe, openScene, person, run, shots, topBar, undoInHeader } from "./support";

/** The Play View at a game: blood, feeding, the Beast and derangements. */

closeContextsAfterEach();

test("the Play View's Sheet tab puts the archetype in the subheader, and says what each trait does", async ({ browser }) => {
  const { page: p } = await person(browser, "play-glossary");
  await p.getByLabel("Name").fill("Footnote");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const id = new URL(p.url()).pathname.split("/")[2]!;
  const put = async (url: string, data: object) => {
    const response = await p.request.put(url, { headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBe(200);
  };
  await put(`/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  await put(`/api/characters/${id}/traits`, { category: "archetype", name: "Loner", rating: null });
  await put(`/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
  await put(`/api/characters/${id}/creation/categories/skills`, { picks: [{ name: "Athletics", rating: 2 }] });
  await put(`/api/characters/${id}/creation/categories/backgrounds`, { picks: [{ name: "Generation", rating: 1 }] });
  await p.goto(`/play/characters/${id}?tab=sheet`);
  await expect(p.getByRole("heading", { name: "Footnote" })).toBeVisible();

  // The clan, archetype and sect are in the subheader, each with an ⓘ, and have no panels of their own.
  await expect(p.getByText("Loner", { exact: true })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Skills" })).toBeVisible();
  for (const part of ["Archetype", "Clan", "Sect"]) await expect(p.getByRole("heading", { name: part, exact: true })).toHaveCount(0);
  await p.getByRole("button", { name: "About Loner" }).click();
  await expect(p.getByText("You can't work within the system.")).toBeVisible();
  await expect(p.getByText("MET: VTM p. 87")).toBeVisible();
  await p.keyboard.press("Escape");
  await p.getByRole("button", { name: "About Brujah" }).click();
  await expect(p.getByText("In-clan disciplines: Celerity, Potence, Presence.")).toBeVisible();
  await p.keyboard.press("Escape");

  // A skill opens to what it lets you do, from the book, with the page.
  await p.getByRole("button", { name: "Athletics", exact: true }).click();
  await expect(p.getByText("Swimming, climbing and jumping are simple actions for you")).toBeVisible();
  await expect(p.getByText("MET: VTM p. 92")).toBeVisible();
  // So does a background, and both stay open.
  await p.getByRole("button", { name: "Generation", exact: true }).click();
  await expect(p.getByText("MET: VTM pp. 100-102")).toBeVisible();
  await expect(p.getByText("Swimming, climbing and jumping are simple actions for you")).toBeVisible();
  await p.screenshot(shots("play-sheet-info"));
});

test("a troupe's house wording on a power shows on the Play View, marked as the troupe's, under the book's summary (#433)", async ({ browser }) => {
  const custodian = await person(browser, "wording-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "wording-lead");
  const player = await person(browser, "wording-player");
  const troupeName = `Hall of Glosses ${run}`;
  const headers = { "X-Horatio": "1" };
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  await backstoryOptional(lead.page, troupeId);

  // The lead gives Presence the troupe's own wording, added to the book's.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/house-rules/book-traits`);
  await l.getByLabel("Category").selectOption({ label: "Disciplines" });
  await l.getByRole("searchbox", { name: "Search book traits" }).fill("presence");
  await l.getByRole("list", { name: "Book traits found" }).getByRole("button", { name: /^Presence/ }).click();
  await l.getByLabel("House wording").fill("Majesty lasts one scene here, not an hour.");
  await expect(l.getByLabel("How players see it")).toContainText("Majesty lasts one scene here, not an hour.");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  const changed = l.locator("section").filter({ has: l.getByRole("heading", { name: "Changed in this troupe", exact: true }) });
  await expect(changed.getByRole("listitem").filter({ hasText: "Presence" })).toContainText("Own wording, added to the book's");

  // A player's Brujah with Presence makes the troupe home.
  const p = player.page;
  const id = await builtVampire(p, "Gloss", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const asked = await p.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBeLessThan(300);
  const [request] = await (await l.request.get(`/api/troupes/${troupeId}/approvals`)).json();
  const approved = await l.request.post(`/api/approvals/${request.id}/approve`, { headers, data: {} });
  expect(approved.status(), await approved.text()).toBeLessThan(300);

  // On the Play View's Sheet tab, Presence opens to the troupe's wording, marked so, under the book's.
  await p.goto(`/play/characters/${id}?tab=sheet`);
  await p.getByRole("button", { name: "Presence", exact: true }).click();
  const wording = p.getByTestId("house-wording");
  await expect(wording).toContainText("House rule");
  await expect(wording).toContainText("Majesty lasts one scene here, not an hour.");
  await p.screenshot(shots("play-house-wording"));

  // The House rules tab lists it under Changed wording.
  await p.goto(`/troupes/${troupeId}/house-rules`);
  const worded = p.locator("section").filter({ has: p.getByRole("heading", { name: "Changed wording", exact: true }) });
  await expect(worded).toContainText("Majesty lasts one scene here, not an hour.");
});

test("a troupe switches Play View tabs off: Pools goes from a player's Play View, and with every tab off its PCs have no Play while staff still run NPCs and scenes (#673)", async ({ browser }) => {
  const custodian = await person(browser, "tabs-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tabs-lead");
  const player = await person(browser, "tabs-player");
  const troupeName = `Paper Court ${run}`;
  const headers = { "X-Horatio": "1" };
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  await backstoryOptional(lead.page, troupeId);

  // A player's Brujah makes the troupe home.
  const l = lead.page;
  const p = player.page;
  const id = await builtVampire(p, "Quire", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const asked = await p.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBeLessThan(300);
  const [request] = await (await l.request.get(`/api/troupes/${troupeId}/approvals`)).json();
  const approved = await l.request.post(`/api/approvals/${request.id}/approve`, { headers, data: {} });
  expect(approved.status(), await approved.text()).toBeLessThan(300);
  // And an NPC the lead runs.
  const npc = await l.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Folio", wizard: false } });
  expect(npc.status(), await npc.text()).toBe(201);
  const folio: string = (await npc.json()).id;

  // Every tab is on until the troupe switches one off.
  await p.goto(`/characters/${id}`);
  await p.getByRole("link", { name: "Play", exact: true }).click();
  const tabs = p.getByRole("tablist", { name: "Play View" });
  await expect(tabs.getByRole("tab", { name: "Pools" })).toBeVisible();

  // The lead switches Pools off in At game's settings, folded at the top of its tab (#784).
  await l.goto(`/troupes/${troupeId}/play#settings`);
  const setting = l.locator("section").filter({ has: l.getByRole("heading", { name: "Play View tabs", exact: true }) });
  const pools = setting.getByRole("checkbox", { name: "Pools", exact: true });
  await expect(pools).toBeChecked();
  await pools.click();
  await expect(pools).not.toBeChecked();

  // The player's Play View has no Pools tab; a link to it opens on the Tracker, as their settings choose.
  await p.goto(`/play/characters/${id}?tab=pools`);
  await expect(tabs.getByRole("tab", { name: "Sheet" })).toBeVisible();
  await expect(tabs.getByRole("tab", { name: "Pools" })).toHaveCount(0);
  await expect(tabs.getByRole("tab", { name: "Tracker" })).toHaveAttribute("aria-selected", "true");
  await p.screenshot(shots("play-tabs-no-pools"));

  // Then every tab off: the last one says what that does before it's saved.
  for (const name of ["Sheet", /^Tracker/, /^Status/, "Equipment"]) {
    const box = setting.getByRole("checkbox", typeof name === "string" ? { name, exact: true } : { name });
    await box.click();
    await expect(box).not.toBeChecked();
  }
  await setting.getByRole("checkbox", { name: "Throws", exact: true }).click();
  const asking = setting.getByRole("alertdialog", { name: "Turn the Play View off for players" });
  await expect(asking).toContainText("the troupe doesn't use the Play View for players: their characters have no Play");
  await expect(asking).toContainText("Staff still run NPCs and scenes");
  await l.screenshot(shots("play-tabs-last-off"));
  await asking.getByRole("button", { name: "Turn the Play View off for players" }).click();
  await expect(setting.getByText("The Play View is off for players.")).toBeVisible();

  // The character has no Play button, and its Play View says why.
  await p.goto(`/characters/${id}`);
  await expect(p.getByRole("heading", { name: /^Quire/ })).toBeVisible();
  await expect(p.getByRole("link", { name: "Play", exact: true })).toHaveCount(0);
  await p.goto(`/play/characters/${id}`);
  await expect(p.getByText("Quire's troupe doesn't use the Play View.")).toBeVisible();

  // The lead still opens the NPC's Play View, with every tab, Pools too.
  await l.goto(`/characters/${folio}`);
  await l.getByRole("link", { name: "Play", exact: true }).click();
  const npcTabs = l.getByRole("tablist", { name: "Play View" });
  await expect(npcTabs.getByRole("tab", { name: "Pools" })).toBeVisible();
  await expect(npcTabs.getByRole("tab", { name: "Tracker" })).toBeVisible();

  // And runs a scene with it from At game.
  await l.goto(`/troupes/${troupeId}/play`);
  await l.getByRole("link", { name: "Open the scenes" }).click();
  await expect(l.getByRole("heading", { name: "Scenes", exact: true })).toBeVisible();
  const sceneId = await openScene(l, troupeId, "The bindery");
  const pinned = await l.request.put(`/api/troupes/${troupeId}/scenes/${sceneId}/characters/${folio}`, { headers });
  expect(pinned.status(), await pinned.text()).toBe(200);
  // A PC with no Play View isn't put in a scene.
  const refused = await l.request.put(`/api/troupes/${troupeId}/scenes/${sceneId}/characters/${id}`, { headers });
  expect(refused.status()).toBe(409);
  await l.reload();
  await expect(l.getByRole("article", { name: "Folio" })).toContainText("Willpower");
});

test("at a game, the Play View tracks blood and uses, offline too, and the storytellers reset the troupe", async ({ browser }) => {
  const custodian = await person(browser, "play-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "play-lead");
  const troupeName = `Court of Candles ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC the lead runs at game, made straight through the API: Generation 2 (12
  // blood, 2 a turn), Herd 2, Physical 5, Social 4, Mental 3, Dodge 2, Intimidation 3
  // and Celerity 2.
  const p = lead.page;
  await (await topBar(p)).getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Lucien", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  for (const [category, name, rating] of [
    ["clan", "Toreador", null],
    ["backgrounds", "Generation", 2],
    ["backgrounds", "Herd", 2],
    ["attributes", "Physical", 5],
    ["attributes", "Social", 4],
    ["attributes", "Mental", 3],
    ["skills", "Dodge", 2],
    ["skills", "Intimidation", 3],
    ["disciplines", "Celerity", 2],
    ["disciplines", "Potence", 2],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category, name, rating, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
  }

  // A house rule: characters start a game with 8 blood.
  await p.goto(`/troupes/${troupeId}/settings`);
  await p.getByRole("button", { name: "Change starting blood" }).click();
  await p.getByLabel("This much:").check();
  await p.getByLabel("Starting blood").fill("8");
  await p.getByRole("button", { name: "Save", exact: true }).click();
  await expect(p.getByText("8 blood, or the generation's most if that is less")).toBeVisible();

  // Play, from the sheet.
  await p.goto(`/characters/${npc}/sheet`);
  await p.getByRole("link", { name: "Play", exact: true }).click();
  await expect(p.getByRole("heading", { name: "Lucien" })).toBeVisible();
  await expect(p.getByLabel("Blood: 8 of 12")).toBeVisible();
  await expect(p.getByText("2 blood a turn")).toBeVisible();
  // The header names the generation two dots of Generation give, not "Generation 2".
  await expect(p.getByText("9th generation")).toBeVisible();
  // Quick notes start on, but Blood, Willpower and healing never stop to ask.
  await expect(p.getByLabel("Quick notes")).toBeChecked();
  await p.getByRole("button", { name: "Spend Blood", exact: true }).click();
  await expect(p.getByLabel("Blood: 7 of 12")).toBeVisible();
  await expect(p.getByRole("dialog", { name: "Note for this spend" })).toHaveCount(0);
  await expect(p.getByText("Blood 8 → 7")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  // The tap says what it did in a toast, with Undo; Undo for it is in the header too.
  await expect(p.getByText("Spent 1 Blood · 7/12")).toBeVisible();
  const header = p.getByRole("banner");
  await expect(await undoInHeader(p, "Blood 8 → 7")).toBeEnabled();
  // The boxes are only to look at: brushing one changes nothing.
  const bloodPanel = p.locator("section").filter({ has: p.getByLabel("Blood: 7 of 12") });
  await bloodPanel.locator("[aria-hidden=true] > span").first().click();
  await bloodPanel.locator("[aria-hidden=true] > span").last().click();
  await expect(p.getByLabel("Blood: 7 of 12")).toBeVisible();
  await expect(p.getByText("Blood 7 → 6")).toHaveCount(0);
  // Humanity's "−" is outlined, not filled red like spending Blood.
  await expect(p.getByRole("button", { name: "Spend Humanity" })).not.toHaveClass(/(^|\s)bg-blood(\s|$)/);
  await expect(p.getByRole("button", { name: "Spend Blood", exact: true })).toHaveClass(/(^|\s)bg-blood(\s|$)/);
  // The screen is kept awake by default; the switch in the header turns it off, remembered on this device.
  const awake = header.getByRole("button", { name: "Keep the screen awake" });
  await expect(awake).toHaveAttribute("aria-pressed", "true");
  await awake.click();
  await expect(awake).toHaveAttribute("aria-pressed", "false");
  await p.reload();
  await expect(awake).toHaveAttribute("aria-pressed", "false");
  await awake.click();
  await expect(awake).toHaveAttribute("aria-pressed", "true");

  await p.getByLabel("Quick notes").uncheck();

  // The Pools tab, loaded once with the page: initiative with and without
  // Celerity, Dodge, and what each power does. The Sheet tab has the stats.
  await p.getByRole("tab", { name: "Pools" }).click();
  const initiative = p.getByRole("listitem").filter({ hasText: /^Initiative/ });
  await expect(initiative.getByText("5", { exact: true })).toBeVisible();
  // The pools come first; the switches are in a drawer from the button at the foot.
  const switches = p.getByRole("button", { name: "Forms, powers and modifiers" });
  await expect(switches).toHaveAccessibleDescription("Nothing in use");
  await expect(switches).toHaveAttribute("aria-expanded", "false");
  await expect(p.getByRole("heading", { name: "Forms and powers in use" })).toHaveCount(0);
  await p.evaluate(() => window.scrollTo(0, 0));
  await expect(p.locator("main section h2").first()).toBeInViewport();
  // It stays at the foot of the screen whatever the scroll, and the last panel clears it.
  await p.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await expect(switches).toBeInViewport();
  const foot = await switches.boundingBox();
  const last = await p.locator("main section").last().boundingBox();
  expect(last!.y + last!.height).toBeLessThanOrEqual(foot!.y);
  await p.evaluate(() => window.scrollTo(0, 0));
  await switches.click();
  await expect(switches).toHaveAttribute("aria-expanded", "true");
  await expect(p.getByRole("dialog", { name: "Forms, powers and modifiers" })).toBeVisible();
  // Celerity switched on: Alacrity adds its two powers to initiative, until it is off.
  await p.getByLabel("Celerity on").check();
  await expect(initiative.getByText("7", { exact: true })).toBeVisible();
  // Taps on any tab say what they did, and Undo is in the header there too.
  await expect(p.getByText("Celerity switched on")).toBeVisible();
  await expect(await undoInHeader(p, /Celerity on/)).toBeEnabled();
  await expect(initiative).toContainText("Physical 5 + Alacrity 2");
  await expect(p.getByRole("region", { name: "Switched on now" })).toContainText("On: Celerity");
  // Without Quickness (#601), nothing more with it.
  await expect(p.getByText(/^Quickness \(p\. 214\)/)).toHaveCount(0);
  await expect(switches).toHaveAccessibleDescription(/In use: Celerity/);
  await p.getByLabel("Celerity on").uncheck();
  await expect(switches).toHaveAccessibleDescription("Nothing in use");
  await expect(initiative.getByText("5", { exact: true })).toBeVisible();
  await expect(p.getByRole("listitem").filter({ hasText: /^Dodge/ }).getByText("7", { exact: true }).first()).toBeVisible();
  await expect(p.getByText("Alacrity", { exact: true })).toBeVisible();
  // Each attack shows what a hit does, with Potence's Might in the breakdown.
  const unarmed = p.getByRole("listitem").filter({ hasText: /^Unarmed attack/ });
  await expect(unarmed.getByText("Damage 2 (1 unarmed + 1 Might) · exceptional 3")).toBeVisible();
  // The Blood rule is said once, over Combat, not under every attack.
  await expect(p.getByText("Spend Blood for +1 Physical each, up to 2 a turn.")).toHaveCount(1);
  // The player's own modifier: Social pools go up while it is on, with Fame in the breakdown.
  const social = p.getByRole("listitem").filter({ hasText: /^Resisting Social powers/ });
  await expect(social).not.toContainText("Fame");
  await p.getByLabel("Your own modifier").fill("Fame");
  await p.getByLabel("Amount").fill("2");
  await p.getByLabel("Applies to").selectOption("Social");
  await p.getByLabel("When (a note)").fill("against mortals");
  await p.getByRole("button", { name: "Add modifier" }).click();
  await expect(social).toContainText("Fame 2");
  await expect(p.getByText("+2 Social pools, against mortals")).toBeVisible();
  await expect(switches).toHaveAccessibleDescription(/In use: \+2 Fame/);
  // Escape closes the drawer and puts focus back on the button; the button opens it again.
  await p.keyboard.press("Escape");
  await expect(p.getByRole("dialog", { name: "Forms, powers and modifiers" })).toHaveCount(0);
  await expect(switches).toBeFocused();
  await switches.click();
  // Switched off, it drops back and waits at the foot of the tab.
  await p.getByLabel("Fame on").click();
  await expect(p.getByLabel("Fame on")).not.toBeChecked();
  await expect(social).not.toContainText("Fame");
  await expect(p.getByRole("heading", { name: "Switched off" })).toBeVisible();
  await p.getByLabel("Fame on").click();
  await expect(social).toContainText("Fame 2");
  await p.keyboard.press("Escape");
  // Other tests (issue #371): attribute + skill, with the player's own modifiers; the
  // storyteller may name another attribute, and one tap counts it.
  const others = p.locator("section").filter({ has: p.getByRole("heading", { name: "Other tests" }) });
  const intimidation = others.getByRole("listitem").filter({ hasText: /^Intimidation/ });
  await expect(intimidation).toContainText("Social 4 + Intimidation 3 + Fame 2");
  await expect(intimidation.getByText("9", { exact: true })).toBeVisible();
  await others.getByRole("button", { name: "Mental", exact: true }).click();
  await expect(intimidation).toContainText("Mental 3 + Intimidation 3");
  await expect(intimidation.getByText("6", { exact: true })).toBeVisible();
  await others.getByRole("button", { name: "As listed" }).click();
  await expect(intimidation.getByText("9", { exact: true })).toBeVisible();
  // Dodge is in Combat, not again here.
  await expect(others.getByRole("listitem").filter({ hasText: /^Dodge/ })).toHaveCount(0);
  await p.screenshot(shots("play-pools"));
  await p.getByRole("tab", { name: "Sheet" }).click();
  await expect(p.getByRole("heading", { name: "Attributes" })).toBeVisible();
  await expect(p.getByRole("tab", { name: "Sheet" })).toHaveAttribute("aria-selected", "true");
  await p.screenshot(shots("play-sheet"));
  await p.getByRole("tab", { name: "Tracker" }).click();

  // No signal: the tap waits on the phone, and goes when the signal returns.
  // The toast's Undo works offline too: the undo waits with it.
  await p.context().setOffline(true);
  await p.getByRole("button", { name: "Spend Blood", exact: true }).click();
  const spent = p.getByText("Spent 1 Blood · 6/12");
  await expect(spent).toBeVisible();
  await p.screenshot(shots("play-toast"));
  await spent.locator("..").getByRole("button", { name: "Undo", exact: true }).click();
  await expect(p.getByText("Undone · Blood 7/12")).toBeVisible();
  await expect(p.getByLabel("Blood: 7 of 12")).toBeVisible();
  await expect(p.getByText("Undid: Blood 7 → 6")).toBeVisible();
  await p.getByRole("button", { name: "Spend Willpower", exact: true }).click();
  await expect(p.getByLabel("Willpower: 5 of 6")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Offline · 3 taps waiting");
  await p.screenshot(shots("play-offline"));
  await p.context().setOffline(false);
  await expect(p.getByRole("status")).toHaveText("Saved");
  // Undo in the header takes it back.
  await (await undoInHeader(p, "Willpower 6 → 5")).click();
  await expect(p.getByText("Undid: Willpower 6 → 5")).toBeVisible();
  await expect(p.getByLabel("Willpower: 6 of 6")).toBeVisible();

  // Quick notes: what a Herd point was for. Then aggravated damage.
  await p.getByLabel("Quick notes").check();
  await p.getByRole("button", { name: "Use Herd" }).click();
  // The note field waits to be tapped, so the keyboard doesn't come up by itself.
  await expect(p.getByLabel(/What was Herd for/)).not.toBeFocused();
  await expect(p.getByRole("dialog").getByRole("button", { name: "Skip the note" })).toBeVisible();
  await p.getByLabel(/What was Herd for/).fill("fed at the club");
  await p.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(p.getByText("Herd 2 → 1")).toBeVisible();
  await expect(p.getByText("“fed at the club”")).toBeVisible();
  await p.getByLabel("Quick notes").uncheck();
  await p.getByRole("button", { name: "+ Aggravated" }).click();
  await expect(p.getByText("Health: took 1 aggravated (0 → 1 marked)")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  // The server has it all: a reload shows the same.
  await p.reload();
  await expect(p.getByLabel("Blood: 7 of 12")).toBeVisible();
  await expect(p.getByText("Backgrounds · 1 of 2 left")).toBeVisible();
  await p.screenshot(shots("play"));

  // After the game the lead resets the whole troupe, from People → At game.
  await p.goto(`/troupes/${troupeId}/play`);
  await expect(p.getByText("Blood 7/12")).toBeVisible();
  await p.getByRole("button", { name: "Reset everyone…" }).click();
  await p.getByRole("button", { name: "Reset everyone for the next game" }).click();
  await expect(p.getByText("1 character was reset.")).toBeVisible();
  await expect(p.getByText("Blood 8/12")).toBeVisible();
  await p.screenshot(shots("play-troupe"));

  // A fresh game, with the last one's log kept.
  await p.getByRole("link", { name: "Lucien" }).click();
  await expect(p.getByLabel("Blood: 8 of 12")).toBeVisible();
  await expect(p.getByText("Game 2")).toBeVisible();
  await p.getByRole("button", { name: /Game 1 ·/ }).click();
  await expect(p.getByText("“fed at the club”")).toBeVisible();

  // The modifier is still there after the Reset, and prints beside the pools it changes while it is on.
  await p.getByRole("tab", { name: "Pools" }).click();
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  await expect(p.getByLabel("Fame on")).toBeChecked();
  await p.goto(`/print/characters/${npc}`);
  await expect(p.getByText("(+2 Fame)", { exact: true })).toBeVisible();
  await expect(p.getByText("2 damage (3 exceptional)", { exact: true })).toBeVisible();
  await p.goBack();

  // With ratings as pips in Settings, the Sheet and Pools tabs show pips too:
  // Physical 5 of ten, Celerity 2, and its powers' levels.
  const asPips = await p.request.patch("/api/preferences", { headers, data: { ratings: "pips" } });
  expect(asPips.status(), await asPips.text()).toBe(200);
  await p.reload();
  await p.getByRole("tab", { name: "Sheet" }).click();
  await expect(p.getByRole("img", { name: "5 dots" }).first()).toBeVisible();
  await expect(p.getByRole("heading", { name: "Attributes" })).toBeVisible();
  await p.screenshot(shots("play-sheet-pips"));
  await p.getByRole("tab", { name: "Pools" }).click();
  await expect(p.getByText("Alacrity", { exact: true })).toBeVisible();
  await expect(p.getByRole("img", { name: "2 dots" }).first()).toBeVisible();
  await p.screenshot(shots("play-pools-pips"));

  // Blood, Willpower and health are in a strip under the tabs here too, and "−" spends from it (#370).
  const strip = p.getByRole("banner").getByRole("group", { name: "Blood, Willpower and health" });
  await expect(strip.getByRole("button", { name: "Blood 8 of 12: open the Tracker" })).toBeVisible();
  await expect(strip.getByRole("button", { name: "Health 0 of 9 marked: open the Tracker" })).toBeVisible();
  await strip.getByRole("button", { name: "Spend Blood" }).click();
  await expect(p.getByText("Spent 1 Blood · 7/12")).toBeVisible();
  await expect(strip.getByRole("button", { name: "Blood 7 of 12: open the Tracker" })).toBeVisible();
  await (await undoInHeader(p, "Blood 8 → 7")).click();
  await expect(strip.getByRole("button", { name: "Blood 8 of 12: open the Tracker" })).toBeVisible();
  // Use on Celerity spends its Blood and switches it on: one tap, with one Undo for both.
  await expect(initiative.getByText("5", { exact: true })).toBeVisible();
  await p.getByRole("button", { name: "Use Celerity, 1 Blood" }).click();
  const used = p.getByText("Spent 1 Blood · 7/12 · Celerity switched on");
  await expect(used).toBeVisible();
  await expect(strip.getByRole("button", { name: "Blood 7 of 12: open the Tracker" })).toBeVisible();
  await expect(initiative.getByText("7", { exact: true })).toBeVisible();
  await expect(p.getByRole("region", { name: "Switched on now" })).toContainText("On: Celerity");
  // The screen as the player sees it, the strip at the top: not a full page, where the sticky header strays.
  await p.evaluate(() => window.scrollTo(0, 0));
  await p.screenshot({ ...shots("play-pools-use"), fullPage: false });
  await used.locator("..").getByRole("button", { name: "Undo", exact: true }).click();
  await expect(p.getByText("Undone · Blood 8/12")).toBeVisible();
  await expect(strip.getByRole("button", { name: "Blood 8 of 12: open the Tracker" })).toBeVisible();
  await expect(initiative.getByText("5", { exact: true })).toBeVisible();
  await expect(p.getByRole("region", { name: "Switched on now" })).toHaveCount(0);
  // Potence's powers cost nothing, so they have no Use button.
  await expect(p.getByRole("button", { name: /^Use Might/ })).toHaveCount(0);
  // A name in the strip opens the Tracker, which has the full trackers and no strip.
  await strip.getByRole("button", { name: "Blood 8 of 12: open the Tracker" }).click();
  await expect(p.getByRole("tab", { name: "Tracker" })).toHaveAttribute("aria-selected", "true");
  await expect(p.getByLabel("Blood: 8 of 12")).toBeVisible();
  await expect(strip).toHaveCount(0);
  await expect(p.getByText("Undid: Celerity on")).toBeVisible();
  await expect(p.getByText("Undid: Blood 8 → 7")).toHaveCount(2);
});

test("Use on an elder power: Projectile spends 1 Blood on each attack, and switches itself on the first time (#588)", async ({ browser }) => {
  const { page: p } = await person(browser, "elder-thrower");
  // A Pretender Elder (Generation 3) with Celerity 5 and its elder power Projectile: Physical 7, Firearms 2.
  const id = await builtVampire(
    p,
    "Hesper",
    "Brujah",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] },
    [
      ["disciplines", "Celerity", 5],
      ["elder_disciplines", "Celerity: Projectile", 1],
    ],
  );
  const blood = (await (await p.request.get(`/api/characters/${id}/play`)).json()).blood;
  const left = (spent: number) => `${blood.value - spent}/${blood.most}`;
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Pools" }).click();
  const firearms = p.getByRole("listitem").filter({ hasText: /^Firearms attack/ });
  await expect(firearms.getByText("9", { exact: true })).toBeVisible();
  // What it does, with its page (#587).
  await expect(p.getByRole("listitem").filter({ hasText: /^Celerity: Projectile/ })).toContainText("1 Blood per thrown or firearms attack: +3 to the attack and 1 more damage, even without the rest of Celerity. (MET: VTM p. 214)");

  // The first Use spends the Blood and switches Projectile on: +3 to the attack.
  const use = p.getByRole("button", { name: "Use Celerity: Projectile, 1 Blood" });
  await use.click();
  await expect(p.getByText(`Spent 1 Blood · ${left(1)} · Celerity: Projectile switched on`)).toBeVisible();
  await expect(firearms.getByText("12", { exact: true })).toBeVisible();
  await expect(p.getByRole("region", { name: "Switched on now" })).toContainText("On: Celerity: Projectile");
  await p.screenshot(shots("play-pools-use-elder"));

  // The next attack pays again, and Projectile stays on.
  await use.click();
  await expect(p.getByText(`Spent 1 Blood on Celerity: Projectile · ${left(2)}`)).toBeVisible();
  await expect(firearms.getByText("12", { exact: true })).toBeVisible();
  await expect(p.getByRole("region", { name: "Switched on now" })).toContainText("On: Celerity: Projectile");
  await expect.poll(async () => (await (await p.request.get(`/api/characters/${id}/play`)).json()).blood.value).toBe(blood.value - 2);
});

test("a power kept until undone: Heart of Darkness's heart stays out through Reset until it is turned off, and Use again asks first (#822)", async ({ browser }) => {
  const { page: p } = await person(browser, "heart-keeper");
  // A Follower of Set with Serpentis 5: Heart of Darkness (core p. 161).
  const id = await builtVampire(
    p,
    "Nebet",
    "Followers of Set",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]], disciplines: [["Obfuscate", 2], ["Presence", 1], ["Serpentis", 1]] },
    [["disciplines", "Serpentis", 5]],
  );
  const headers = { "X-Horatio": "1" };
  const reset = async () => {
    const response = await p.request.post(`/api/characters/${id}/play/reset`, { headers, data: {} });
    expect(response.status(), await response.text()).toBe(200);
    await p.reload();
  };
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Pools" }).click();
  await p.getByRole("button", { name: /^Use Heart of Darkness: heart removed, 1 Blood/ }).click();
  await expect(p.getByText(/Heart of Darkness: heart removed switched on/)).toBeVisible();
  const banner = p.getByRole("region", { name: "Switched on now" });
  await expect(banner).toContainText("Kept: Heart of Darkness: heart removed");

  // Reset ends the game, but the heart stays out.
  await reset();
  await p.getByRole("tab", { name: "Pools" }).click();
  await expect(banner).toContainText("Kept: Heart of Darkness: heart removed");
  const switches = p.getByRole("button", { name: "Forms, powers and modifiers" });
  await switches.click();
  const drawer = p.getByRole("dialog", { name: "Forms, powers and modifiers" });
  await expect(drawer.getByLabel("Heart of Darkness: heart removed on")).toBeChecked();
  await expect(drawer).toContainText("Kept through Reset until you turn it off.");
  await expect(drawer).toContainText("Frenzy resisted as if with 1 Beast trait fewer");
  await drawer.getByRole("button", { name: "Close" }).first().click();

  // Using it again replaces it, so it asks first.
  await p.getByRole("button", { name: /^Use Heart of Darkness: heart removed, 1 Blood/ }).click();
  const again = p.getByRole("dialog", { name: "Use it again?" });
  await expect(again).toContainText("Using it again replaces it: a character carries one at a time.");
  await again.getByRole("button", { name: "Cancel" }).click();
  await expect(again).toBeHidden();

  // Turned off, it stays off through the next Reset.
  await banner.getByRole("button", { name: "Switch Heart of Darkness: heart removed off" }).click();
  await expect(banner).toHaveCount(0);
  await reset();
  await p.getByRole("tab", { name: "Pools" }).click();
  await expect(banner).toHaveCount(0);
});

test("defences that aren't a flat bonus: Rampart of Faith follows Morality and Beast traits, Rockheart resists with Physical + Survival (#602)", async ({ browser }) => {
  const { page: p } = await person(browser, "rampart-keeper");
  const pool = (name: string) => p.getByRole("listitem").filter({ hasText: new RegExp(`^${name}`) });
  const play = async (id: string) => (await (await p.request.get(`/api/characters/${id}/play`)).json()) as { willpower: { value: number }; blood: { value: number; most: number } };

  // A Salubri Pretender Elder with Valeren 5 and Rampart of Faith: Mental 3, Humanity 5, no Beast traits.
  const salubri = await builtVampire(
    p,
    "Ithiel",
    "Salubri",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 3], ["Fame", 2], ["Resources", 1]], disciplines: [["Valeren", 2], ["Auspex", 1], ["Fortitude", 1]] },
    [
      ["disciplines", "Valeren", 5],
      ["elder_disciplines", "Valeren: Rampart of Faith", 1],
    ],
  );
  const { willpower, blood } = await play(salubri);
  await p.goto(`/play/characters/${salubri}`);
  await p.getByRole("tab", { name: "Pools" }).click();
  // Each defence counts Willpower, so each offers Rampart of Faith for 1 Blood: Humanity 5 − 0 Beast traits.
  const mental = pool("Resisting Mental powers");
  await expect(mental.getByText(String(3 + willpower.value), { exact: true })).toBeVisible();
  const rampart = mental.getByRole("listitem").filter({ hasText: "For 1 Blood" });
  await expect(rampart).toContainText("(+5 Rampart of Faith)");
  await expect(rampart.getByText(String(3 + willpower.value + 5), { exact: true })).toBeVisible();
  for (const name of ["Resisting Social powers", "Resisting Physical powers"]) await expect(pool(name)).toContainText("(+5 Rampart of Faith)");
  await expect(p.getByText(/Instead, with Rockheart/)).toHaveCount(0);
  // Using it spends the Blood.
  await p.getByRole("button", { name: "Use Valeren: Rampart of Faith, 1 Blood" }).click();
  await expect(p.getByText(`Spent 1 Blood on Valeren: Rampart of Faith · ${blood.value - 1}/${blood.most}`)).toBeVisible();
  await p.screenshot(shots("play-pools-rampart"));

  // A Beast trait takes one off it.
  await p.getByRole("tab", { name: "Tracker" }).click();
  await p.getByRole("button", { name: "Gain a Beast traits point" }).click();
  await expect(p.getByLabel("Beast traits: 1 of 5")).toBeVisible();
  await p.getByRole("tab", { name: "Pools" }).click();
  await expect(rampart).toContainText("(+4 Rampart of Faith)");
  await expect(rampart.getByText(String(3 + willpower.value + 4), { exact: true })).toBeVisible();

  // A Gargoyle Luminary Elder with Rockheart: Physical 7, Survival 4.
  const skills = ATTRIBUTES_AND_FOCUSES.skills!.filter(([name]) => name !== "Brawl");
  const gargoyle = await builtVampire(
    p,
    "Petronel",
    "Gargoyles",
    { ...ATTRIBUTES_AND_FOCUSES, skills: [["Survival", 4], ...skills], backgrounds: [["Generation", 3], ["Fame", 2], ["Herd", 1]], disciplines: [["Visceratika", 2], ["Fortitude", 1], ["Potence", 1]] },
    [
      ["backgrounds", "Generation", 4],
      ["backgrounds", "Generation", 5],
      ["disciplines", "Visceratika", 5],
      ["luminary_disciplines", "Visceratika: Rockheart", 1],
    ],
  );
  await p.goto(`/play/characters/${gargoyle}`);
  await p.getByRole("tab", { name: "Pools" }).click();
  // Mental and Social defence offer Physical + Survival instead, without Willpower; Physical defence doesn't.
  for (const name of ["Resisting Mental powers", "Resisting Social powers"]) {
    const instead = pool(name).getByRole("listitem").filter({ hasText: "Instead, with Rockheart" });
    await expect(instead).toContainText("(Physical 7 + Survival 4)");
    await expect(instead.getByText("11", { exact: true })).toBeVisible();
  }
  await expect(pool("Resisting Physical powers")).not.toContainText("Rockheart");
  await expect(pool("Resisting Social powers")).toContainText("A Willpower spent to retest a Social power comes straight back (Rockheart)");
  await expect(p.getByText("Rockheart: 1 Blood wins a frenzy test outright")).toBeVisible();
  await expect(p.getByText(/For 1 Blood/)).toHaveCount(0);
  await p.screenshot(shots("play-pools-rockheart"));
});

test("Flesh of Marble: two Protective Gear qualities picked each use, each against the attacks it guards (#599)", async ({ browser }) => {
  const { page: p } = await person(browser, "marble-skin");
  // A Gangrel elder (Generation 3) with Protean 5 and Flesh of Marble (Vol. 2 p. 232).
  const id = await builtVampire(
    p,
    "Galatea",
    "Gangrel",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]], disciplines: [["Protean", 2], ["Animalism", 1], ["Fortitude", 1]] },
    [
      ["disciplines", "Protean", 5],
      ["elder_disciplines", "Protean: Flesh of Marble", 1],
    ],
  );
  await p.goto(`/play/characters/${id}?tab=pools`);
  const row = (name: RegExp) => p.getByRole("main").getByRole("listitem").filter({ hasText: name }).first();
  const dodge = row(/^Dodge/);
  await expect(dodge).toBeVisible();
  const before = Number(await dodge.locator("strong").first().textContent());
  const against = (attacks: RegExp) => dodge.getByRole("listitem").filter({ hasText: attacks });

  // Use spends its Blood and switches it on; its qualities are picked in the drawer.
  await p.getByRole("button", { name: "Use Protean: Flesh of Marble, 1 Blood" }).click();
  await expect(p.getByText(/Protean: Flesh of Marble switched on$/)).toBeVisible();
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  const qualities = p.getByRole("group", { name: "Protean: Flesh of Marble: qualities" });
  await expect(qualities).toContainText("Pick two each use (0 picked).");
  await qualities.getByRole("button", { name: "Ballistic" }).click();
  await expect(p.getByText("Picked Ballistic for Protean: Flesh of Marble", { exact: true })).toBeVisible();
  await qualities.getByRole("button", { name: "Rugged" }).click();
  await expect(qualities).toContainText("Rugged: The first Physical hit does 2 less damage (MET: VTM p. 519)");

  // Ballistic: +3 against firearms and +1 against the rest, each a line under Dodge; Dodge itself stays.
  await expect(against(/^Against firearms/)).toContainText("(+3 Flesh of Marble: Ballistic)");
  await expect(against(/^Against firearms/).locator("strong")).toHaveText(String(before + 3));
  await expect(against(/^Against Brawl, Melee and thrown weapons/).locator("strong")).toHaveText(String(before + 1));
  await expect(dodge.locator("strong").first()).toHaveText(String(before));

  // A third drops the oldest: Hardened in Ballistic's place turns the split round.
  await qualities.getByRole("button", { name: "Hardened" }).click();
  await expect(p.getByText("Picked Hardened for Protean: Flesh of Marble: dropped Ballistic (2 at most)")).toBeVisible();
  await expect(qualities.getByRole("button", { name: "Ballistic" })).toHaveAttribute("aria-pressed", "false");
  await expect(against(/^Against firearms/).locator("strong")).toHaveText(String(before + 1));
  await expect(against(/^Against Brawl, Melee and thrown weapons/)).toContainText("(+3 Flesh of Marble: Hardened)");
  await expect(against(/^Against Brawl, Melee and thrown weapons/).locator("strong")).toHaveText(String(before + 3));
  await p.getByRole("dialog", { name: "Forms, powers and modifiers" }).getByRole("button", { name: "Close" }).click();
  await expect(p.getByRole("region", { name: "Switched on now" })).toContainText("On: Protean: Flesh of Marble (Rugged, Hardened)");
  await p.screenshot(shots("play-pools-flesh-of-marble"));

  // Switched off, the qualities go with it, and using it again means picking again.
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  await p.getByLabel("Protean: Flesh of Marble on").uncheck();
  await expect(against(/^Against/)).toHaveCount(0);
  await p.getByLabel("Protean: Flesh of Marble on").check();
  await expect(qualities).toContainText("(0 picked)");
});

test("timed powers as switches: Armor of Terra's own qualities under Dodge, and Fleshcraft's attack in Combat (#820)", async ({ browser }) => {
  const { page: p } = await person(browser, "terra-flesh");
  // A Gargoyle elder (Generation 3) with Visceratika 4.
  const id = await builtVampire(
    p,
    "Zdenek",
    "Gargoyles",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]], disciplines: [["Visceratika", 2], ["Fortitude", 1], ["Potence", 1]] },
    [["disciplines", "Visceratika", 4]],
  );
  await p.goto(`/play/characters/${id}?tab=pools`);
  const row = (name: RegExp) => p.getByRole("main").getByRole("listitem").filter({ hasText: name }).first();
  const dodge = row(/^Dodge/);
  await expect(dodge).toBeVisible();
  const before = Number(await dodge.locator("strong").first().textContent());
  const against = (attacks: RegExp) => dodge.getByRole("listitem").filter({ hasText: attacks });

  // Armor of Terra (core p. 171): Hardened and Ballistic without picking, each a line under Dodge.
  await p.getByRole("button", { name: "Use Armor of Terra, 1 Blood" }).click();
  await expect(p.getByText(/Armor of Terra switched on$/)).toBeVisible();
  await expect(against(/^Against firearms/)).toContainText("+1 Armor of Terra: Hardened");
  await expect(against(/^Against firearms/)).toContainText("+3 Armor of Terra: Ballistic");
  await expect(against(/^Against firearms/).locator("strong")).toHaveText(String(before + 4));
  await expect(against(/^Against Brawl, Melee and thrown weapons/).locator("strong")).toHaveText(String(before + 4));
  await expect(dodge.locator("strong").first()).toHaveText(String(before));

  const switches = p.getByRole("button", { name: "Forms, powers and modifiers" });
  await switches.click();
  const drawer = p.getByRole("dialog", { name: "Forms, powers and modifiers" });
  await expect(drawer).toContainText("Hardened, Ballistic");
  // Switched off, its qualities go.
  await p.getByLabel("Armor of Terra on").uncheck();
  await drawer.getByRole("button", { name: "Close" }).click();
  await expect(against(/^Against/)).toHaveCount(0);

  // A Tzimisce with Vicissitude 2: Fleshcraft (core p. 168) is a Brawl attack in Combat while it's on, 1 damage nothing reduces.
  const tzimisce = await builtVampire(
    p,
    "Vaclava",
    "Tzimisce",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]], disciplines: [["Vicissitude", 2], ["Animalism", 1], ["Auspex", 1]] },
    [],
  );
  await p.goto(`/play/characters/${tzimisce}?tab=pools`);
  await expect(row(/^Dodge/)).toBeVisible();
  const flesh = p.getByRole("listitem").filter({ hasText: /^Fleshcraft attack/ });
  await expect(flesh).toHaveCount(0);
  await p.getByRole("button", { name: "Use Fleshcraft, 1 Blood" }).click();
  await expect(flesh).toContainText("against Physical + Dodge");
  await expect(flesh).toContainText("Damage 1, nothing reduces it · exceptional 2");
  await switches.click();
  await expect(drawer).toContainText("Fleshcraft attack in Combat: 1 damage that nothing reduces");
  await p.getByLabel("Fleshcraft on").uncheck();
  await drawer.getByRole("button", { name: "Close" }).click();
  await expect(flesh).toHaveCount(0);
});

test("Azhi Dahaka gives every attribute focus: on the sheet and the Play View, from the power, and counted in its powers (#598)", async ({ browser }) => {
  const { page: p } = await person(browser, "azhi-seeker");
  // A Tzimisce Luminary Elder (Generation 5) with Vicissitude 5, whose own Social focus is Manipulation.
  const id = await builtVampire(
    p,
    "Vasilisa",
    "Tzimisce",
    {
      ...ATTRIBUTES_AND_FOCUSES,
      focus_socials: [["Manipulation", 1]],
      backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]],
      disciplines: [["Vicissitude", 2], ["Animalism", 1], ["Auspex", 1]],
    },
    [
      ["disciplines", "Vicissitude", 5],
      ["backgrounds", "Generation", 5],
      ["luminary_disciplines", "Vicissitude: Azhi Dahaka", 1],
    ],
  );

  // The sheet has every focus, those it lacked marked as given by the power.
  await p.goto(`/characters/${id}`);
  const row = (name: string) => p.locator("main li").filter({ hasText: new RegExp(`^${name}(?![a-z])`) });
  for (const focus of ["Dexterity", "Stamina", "Appearance", "Charisma", "Intelligence", "Perception"]) await expect(row(focus)).toContainText("from Vicissitude: Azhi Dahaka");
  await expect(row("Manipulation")).not.toContainText("from Vicissitude: Azhi Dahaka");

  // The Play View's Sheet tab lists them by attribute, and says which the power gives.
  await p.goto(`/play/characters/${id}?tab=sheet`);
  await expect(p.getByText("(Appearance, Charisma, Manipulation)")).toBeVisible();
  await p.getByRole("button", { name: /^Social/ }).click();
  await expect(p.getByText("Charisma (from Vicissitude: Azhi Dahaka): Charm and the force of your personality.", { exact: false })).toBeVisible();
  await expect(p.getByText("Manipulation: Getting people to do what you want", { exact: false })).toBeVisible();

  // On the Pools tab, Vicissitude's powers say what the focuses add: Malleable Visage's Charisma.
  await p.getByRole("tab", { name: "Pools" }).click();
  await expect(p.getByText("Your focus: One standard action, no hands needed.")).toBeVisible();
  await p.screenshot(shots("play-pools-azhi-dahaka"));
});

test("a power that hurts through its own test: Psychic Assault's pool and damage show beside the attacks once it's used, until it's off (#600)", async ({ browser }) => {
  const { page: p } = await person(browser, "elder-assault");
  // A Pretender Elder (Generation 3) with Auspex 5 and its elder power Psychic Assault: Mental 3, Investigation 1.
  const id = await builtVampire(
    p,
    "Ilaria",
    "Toreador",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]], disciplines: [["Auspex", 2], ["Celerity", 1], ["Presence", 1]] },
    [
      ["disciplines", "Auspex", 5],
      ["elder_disciplines", "Auspex: Psychic Assault", 1],
    ],
  );
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Pools" }).click();
  await expect(p.getByRole("listitem").filter({ hasText: /^Unarmed attack/ })).toBeVisible();
  const assault = p.getByRole("listitem").filter({ hasText: /^Psychic Assault/ });
  await expect(assault).toHaveCount(0);

  // Use spends the Blood and switches it on: the Auspex test pool, and 4 damage nothing reduces (core p. 213).
  await p.getByRole("button", { name: "Use Auspex: Psychic Assault, 1 Blood" }).click();
  await expect(p.getByText(/Spent 1 Blood · \d+\/\d+ · Auspex: Psychic Assault switched on/)).toBeVisible();
  await expect(assault.getByText("4", { exact: true })).toBeVisible();
  await expect(assault).toContainText("Mental 3 + Investigation 1 · against Mental + Willpower");
  await expect(assault).toContainText("Damage 4, nothing reduces it · exceptional 5");
  await p.screenshot(shots("play-pools-power-damage"));

  // The drawer says what its switch does; switched off, the pool goes.
  const switches = p.getByRole("button", { name: "Forms, powers and modifiers" });
  await switches.click();
  await expect(p.getByRole("dialog", { name: "Forms, powers and modifiers" })).toContainText("Psychic Assault in Combat: 4 damage that nothing reduces");
  await p.getByLabel("Auspex: Psychic Assault on").uncheck();
  await expect(switches).toHaveAccessibleDescription("Nothing in use");
  await expect(assault).toHaveCount(0);
});

test("an elder power adds its notes to another power's switch: Quickness with Celerity (#601)", async ({ browser }) => {
  const { page: p } = await person(browser, "quick-elder");
  // A Pretender Elder (Generation 3) with Celerity 5 and its elder power Quickness.
  const id = await builtVampire(
    p,
    "Lark",
    "Brujah",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] },
    [
      ["disciplines", "Celerity", 5],
      ["elder_disciplines", "Celerity: Quickness", 1],
    ],
  );
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Pools" }).click();
  const quickness = "Quickness (p. 214): An extra round of actions, one simple and one standard, taken in the third Celerity round.";
  // With Celerity's switch, under the power's name and page.
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  const drawer = p.getByRole("dialog", { name: "Forms, powers and modifiers" });
  await expect(drawer.getByRole("listitem").filter({ hasText: /^Celerity/ })).toContainText(quickness);
  await expect(p.getByRole("region", { name: "Switched on now" })).toHaveCount(0);
  // Switched on, it is in the banner too, and goes with it.
  await drawer.getByLabel("Celerity on").check();
  const banner = p.getByRole("region", { name: "Switched on now" });
  await expect(banner).toContainText("On: Celerity");
  await expect(banner).toContainText(quickness);
  await drawer.getByLabel("Celerity on").uncheck();
  await expect(banner).toHaveCount(0);
  // Each power on has its own Off in the banner, which works like its switch (#697).
  await drawer.getByLabel("Celerity on").check();
  await drawer.getByRole("button", { name: "Close" }).click();
  await banner.getByRole("button", { name: "Switch Celerity off" }).click();
  await expect(banner).toHaveCount(0);
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  await expect(drawer.getByLabel("Celerity on")).not.toBeChecked();
});

test("Killer Instincts: +2 Accurate and Brutal on a line of their own against the hunted target, on the Play View and in a Scene (#613)", async ({ browser }) => {
  const custodian = await person(browser, "instinct-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "instinct-lead");
  const troupeName = `Ashen Spoor ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC with Killer Instincts (Vol. 2 p. 84): Physical 5, Brawl 3, Melee 2, Firearms 1, Athletics 1.
  const p = lead.page;
  await (await topBar(p)).getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Sefa", wizard: false } });
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
    ["elder_disciplines", "Spiritus: Killer Instincts", 1],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category, name, rating, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
  }

  // Off, each attack is as it was, with no line for the hunted target.
  await p.goto(`/play/characters/${npc}?tab=pools`);
  await expect(p.getByRole("heading", { name: "Sefa" })).toBeVisible();
  const attacks = { "Unarmed attack": 8, "Melee attack": 7, "Firearms attack": 6, "Thrown or bow attack": 6 };
  const row = (name: string) => p.getByRole("main").getByRole("listitem").filter({ hasText: new RegExp(`^${name}`) }).first();
  const hunted = (name: string) => row(name).getByRole("listitem").filter({ hasText: /^Against your hunted target/ });
  await expect(row("Unarmed attack").locator("strong").first()).toHaveText("8");
  await expect(p.getByText(/Against your hunted target/)).toHaveCount(0);

  // On, the totals stay, and each Physical attack has its line: +2 Accurate, and Brutal with what it does (core p. 516).
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  const drawer = p.getByRole("dialog", { name: "Forms, powers and modifiers" });
  await expect(drawer).toContainText("Against your hunted target: +2 attacks (Accurate), Brutal");
  await drawer.getByLabel("Spiritus: Killer Instincts on").check();
  await drawer.getByRole("button", { name: "Close" }).click();
  for (const [name, total] of Object.entries(attacks)) {
    await expect(row(name).locator("strong").first()).toHaveText(String(total));
    await expect(hunted(name)).toContainText("Against your hunted target (+2 Accurate), Brutal");
    await expect(hunted(name).locator("strong")).toHaveText(String(total + 2));
    await expect(hunted(name)).toContainText("Brutal: win on the larger pool: exceptional success (p. 516)");
  }
  await expect(row("Dodge")).not.toContainText("hunted target");
  await p.screenshot(shots("play-pools-killer-instincts"));

  // The Scene view's pools list shows the same line.
  const scene = await p.context().newPage();
  await openScene(scene, troupeId, "Sefa's quarry");
  await scene.getByRole("combobox", { name: "Add to the scene" }).fill("Sefa");
  await scene.getByRole("option", { name: /Sefa/ }).click();
  const card = scene.getByRole("article", { name: "Sefa" });
  await expect(card).toContainText("Attack Unarmed 8 (1 dmg) · Melee 7");
  await card.getByRole("button", { name: /^Pools/ }).click();
  const unarmed = card.getByRole("region", { name: "Combat" }).getByRole("listitem").filter({ hasText: /^Unarmed attack/ }).first();
  const line = unarmed.getByRole("listitem").filter({ hasText: /^Against your hunted target/ });
  await expect(line).toContainText("Against your hunted target (+2 Accurate), Brutal");
  await expect(line.locator("strong")).toHaveText("10");
  await expect(line).toContainText("Brutal: win on the larger pool: exceptional success (p. 516)");
  await scene.close();

  // Off again, the lines go.
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  await drawer.getByLabel("Spiritus: Killer Instincts on").uncheck();
  await expect(p.getByText(/Against your hunted target \(/)).toHaveCount(0);
});

test("kept on the phone, a player's character opens with no signal: the sheet, the Play View and its powers, and taps go when the signal returns (#502)", async ({ browser }) => {
  // The player's own phone, with the service worker that keeps the app, and asked the first time they sign in.
  const { page: p } = await person(browser, "offline-keeper", { serviceWorkers: "allow", storageState: { cookies: [], origins: [] } });
  const question = p.getByRole("dialog", { name: "Your own phone?" });
  await expect(question).toContainText("Is this your own phone?");
  const id = await builtVampire(p, "Nocturne", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  await question.getByRole("button", { name: "Yes, keep them here" }).click();
  await expect(question).toBeHidden();

  // Account › This device says what is kept here.
  await p.goto("/account/device");
  await expect(p.getByRole("radio", { name: "On: my characters work offline" })).toHaveAttribute("aria-checked", "true");
  const kept = p.getByRole("group", { name: "Kept on this device" });
  await p.getByRole("button", { name: "Update now" }).click();
  await expect(kept).toContainText("Kept here now: Nocturne");
  await expect(kept).toContainText(/Updated .* · about \d+ KB/);
  // Everything kept came: no word of screens left as they were (#619).
  await expect(kept).not.toContainText("The last try");
  await p.screenshot(shots("offline-device"));
  await p.evaluate(async () => void (await navigator.serviceWorker.ready));

  // No signal: the app opens to the player's characters, kept on the phone.
  await p.context().setOffline(true);
  await p.goto("/characters");
  await expect(p.getByRole("heading", { name: "Your characters" })).toBeVisible();
  await expect(p.getByLabel("Connection")).toContainText(/^Offline · your characters as of /);
  await p.getByRole("link", { name: /Nocturne/ }).click();
  await expect(p.getByRole("heading", { name: /Nocturne/ })).toBeVisible();
  await expect(p.getByText("Brawl", { exact: true }).first()).toBeVisible();
  // A screen between games needs a connection, and says so.
  await characterTab(p, "Downtime");
  await expect(p.getByText("The Downtime tab needs a connection.")).toBeVisible();
  await p.screenshot(shots("offline-needs-connection"));

  // The Play View: a tap waits on the phone, through a reload, and the powers are there.
  await p.goto(`/play/characters/${id}`);
  await expect(p.getByRole("heading", { name: "Nocturne" })).toBeVisible();
  await p.getByRole("button", { name: "Spend Willpower", exact: true }).click();
  await expect(p.getByRole("status")).toHaveText("Offline · 1 tap waiting");
  await expect(p.getByText(/^Your sheet as of /)).toBeVisible();
  await p.reload();
  await expect(p.getByRole("status")).toHaveText("Offline · 1 tap waiting");
  await p.getByRole("button", { name: "Spend Willpower", exact: true }).click();
  await expect(p.getByRole("status")).toHaveText("Offline · 2 taps waiting");
  await p.getByRole("tab", { name: "Pools" }).click();
  await expect(p.getByText("Celerity", { exact: true }).first()).toBeVisible();
  await p.screenshot(shots("offline-play"));

  // The signal returns: the taps go.
  await p.context().setOffline(false);
  await expect(p.getByRole("status")).toHaveText("Saved");
  const view = await (await p.request.get(`/api/characters/${id}/play`)).json();
  expect(view.willpower.value).toBe(view.willpower.most - 2);

  // Signing out with a tap not yet sent warns first, then clears the phone.
  const me = await (await p.request.get("/api/auth/me")).json();
  await p.route("**/play/taps", (route) => route.fulfill({ status: 503, json: { detail: "Down for a moment." } }));
  await p.getByRole("tab", { name: "Tracker" }).click();
  await p.getByRole("button", { name: "Spend Willpower", exact: true }).click();
  await expect(p.getByRole("status")).toHaveText("Saving · 1 tap waiting");
  await p.goto("/characters");
  await (await topBar(p)).getByRole("button", { name: "Sign out" }).click();
  const leaving = p.getByRole("dialog", { name: "Sign out?" });
  await expect(leaving).toContainText("1 tap hasn't been sent yet. Sign out anyway?");
  await leaving.getByRole("button", { name: "Sign out anyway" }).click();
  await expect(p.getByRole("heading", { name: "Sign in" })).toBeVisible();
  expect(await p.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("horatio.play.") || k === "horatio.offline.who"))).toEqual([]);
  const left = await p.evaluate(
    (key) =>
      new Promise((done) => {
        const opened = indexedDB.open("horatio-offline");
        opened.onsuccess = () => {
          const got = opened.result.transaction("kept").objectStore("kept").get(key);
          got.onsuccess = () => done(got.result ?? null);
        };
      }),
    `person:${me.id}`,
  );
  expect(left).toBeNull();
});

test("online only, nothing is kept: with no signal, the app says it needs a connection (#502)", async ({ browser }) => {
  // A browser that answered "No, online only" (the suite's), with the service worker.
  const { page: p } = await person(browser, "offline-borrow", { serviceWorkers: "allow" });
  await p.goto("/account/device");
  await expect(p.getByRole("radio", { name: "Off: online only" })).toHaveAttribute("aria-checked", "true");
  await expect(p.getByText("Nothing is kept here. For a borrowed or shared phone.")).toBeVisible();
  await p.evaluate(async () => void (await navigator.serviceWorker.ready));
  await p.context().setOffline(true);
  await p.reload();
  await expect(p.getByText("Your account needs a connection.")).toBeVisible();
  await p.goto("/characters");
  await expect(p.getByText("The Characters page needs a connection.")).toBeVisible();
});

test("Throws on the Play View: rock, paper or scissors, the last three kept, with no signal too, and the Play View can open on it (#668)", async ({ browser }) => {
  const { page: p } = await person(browser, "rps-thrower");
  await p.getByLabel("Name").fill("Corvina");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const id = new URL(p.url()).pathname.split("/")[2]!;
  const thrown = /^(Rock|Paper|Scissors)$/;

  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Throws" }).click();
  const throws = p.getByRole("region", { name: "Throws" });
  await expect(throws).toContainText("Throw for rock, paper or scissors");
  await throws.getByRole("button", { name: "Throw" }).click();
  // The count-in, then the throw, large, with its word, and the word again upside
  // down above it for the player across the table (#740).
  await expect(throws.getByRole("img", { name: thrown })).toBeVisible();
  const word = (await throws.getByRole("img", { name: thrown }).getAttribute("aria-label"))!;
  await expect(throws.getByTestId("throw-word-flipped")).toHaveText(word);
  await expect(throws.getByRole("img", { name: thrown }).getByText(word, { exact: true })).toHaveCount(2);
  const past = throws.getByRole("region", { name: "Last throws" }).getByRole("listitem");
  await expect(past).toHaveCount(1);
  // On a small phone the throw, both words and the Throw button fit without scrolling.
  const size = p.viewportSize()!;
  await p.setViewportSize({ width: 375, height: 667 });
  await p.evaluate(() => window.scrollTo(0, 0));
  await expect(throws.getByTestId("throw-word-flipped")).toBeInViewport();
  await expect(throws.getByRole("img", { name: thrown }).getByText(word, { exact: true }).last()).toBeInViewport();
  await expect(throws.getByRole("button", { name: "Throw" })).toBeInViewport();
  await p.screenshot({ ...shots("throws-small-phone"), animations: "disabled" });
  await p.setViewportSize(size);

  // Nothing goes to the server, so it throws with no signal.
  await p.context().setOffline(true);
  for (const count of [2, 3, 3]) {
    await throws.getByRole("button", { name: "Throw" }).click();
    await expect(throws.getByRole("button", { name: "Throw" })).toBeEnabled();
    await expect(past).toHaveCount(count);
  }
  await expect(throws.getByRole("img", { name: thrown })).toBeVisible();
  await expect(past.first()).toContainText(/Rock|Paper|Scissors/);
  await p.context().setOffline(false);
  await p.screenshot({ ...shots("throws"), animations: "disabled" });

  // Settings › the Play View opens on Throws, here in Ultra goth.
  await p.goto("/account/settings");
  const saved = p.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.ok());
  await p.getByRole("radiogroup", { name: "The Play View opens on" }).getByRole("radio", { name: "Throws" }).click();
  await saved;
  const goth = await p.request.patch("/api/preferences", { headers: { "X-Horatio": "1" }, data: { theme: "ultragoth" } });
  expect(goth.status(), await goth.text()).toBe(200);
  await p.goto(`/play/characters/${id}`);
  await expect(p.locator("html")).toHaveAttribute("data-theme", "ultragoth");
  await expect(p.getByRole("tab", { name: "Throws" })).toHaveAttribute("aria-selected", "true");
  // The last throws stay for the browser tab.
  await expect(past).toHaveCount(3);
  await throws.getByRole("button", { name: "Throw" }).click();
  await expect(throws.getByRole("button", { name: "Throw" })).toBeEnabled();
  await expect(throws.getByRole("img", { name: thrown })).toBeVisible();
  await p.screenshot({ ...shots("throws-ultragoth"), animations: "disabled" });
});

test("a troupe uploads its own rock, paper and scissors, names the set and previews it in Dark and Ultra goth (#670)", async ({ browser }) => {
  const custodian = await person(browser, "throwpix-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "throwpix-lead");
  const headers = { "X-Horatio": "1" };
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Bone Throwers ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/play#settings`);
  const card = l.locator("section").filter({ has: l.getByRole("heading", { name: "Throw pictures", exact: true }) });
  await expect(card.getByText("None yet")).toHaveCount(3);

  // A small PNG for each: Horatio keeps it whole on a transparent square.
  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
  for (const which of ["Rock", "Paper"]) {
    await card.getByLabel(`Choose a picture for ${which}`).setInputFiles({ name: `${which}.png`, mimeType: "image/png", buffer: png });
    await expect(card.getByRole("img", { name: `The troupe's ${which.toLowerCase()}` })).toBeVisible();
  }
  await expect(card.getByText("Add the rest: the set is offered only with all three.")).toBeVisible();
  await card.getByLabel("Choose a picture for Scissors").setInputFiles({ name: "Scissors.png", mimeType: "image/png", buffer: png });
  await expect(card.getByRole("img", { name: "The troupe's scissors" })).toBeVisible();
  await expect(card.getByText("Add the rest: the set is offered only with all three.")).toHaveCount(0);

  await card.getByLabel(/Title for the set/).fill("Land of the Sky bones");
  await card.getByRole("button", { name: "Use this title" }).click();
  await expect(card.getByRole("button", { name: "Use this title" })).toBeDisabled();

  // The preview shows all three as the Throws tab would, in Dark, then Ultra goth.
  const preview = card.getByRole("region", { name: "Preview" });
  for (const which of ["Rock", "Paper", "Scissors"]) await expect(preview.getByRole("img", { name: which, exact: true })).toBeVisible();
  const panel = preview.getByTestId("throw-preview");
  await expect(panel).toHaveCSS("background-color", "rgb(30, 25, 34)");
  await preview.getByRole("radio", { name: "Ultra goth" }).check();
  await expect(panel).toHaveCSS("background-color", "rgb(19, 16, 17)");

  // Replacing one keeps the set; removing the set goes back to Horatio's.
  const old = await card.getByRole("img", { name: "The troupe's rock" }).getAttribute("src");
  await card.getByLabel("Choose a picture for Rock").setInputFiles({ name: "Rock2.png", mimeType: "image/png", buffer: png });
  await expect(card.getByRole("img", { name: "The troupe's rock" })).not.toHaveAttribute("src", old!);
  await card.getByRole("button", { name: "Remove the set" }).click();
  await card.getByRole("alertdialog", { name: "Remove the throw pictures" }).getByRole("button", { name: "Remove them" }).click();
  await expect(card.getByText("None yet")).toHaveCount(3);
  await expect(card.getByRole("region", { name: "Preview" })).toHaveCount(0);

  await l.goto(`/troupes/${troupeId}/log`);
  await expect(l.getByText("gave the troupe a new picture for Rock.")).toBeVisible();
  await expect(l.getByText("named the troupe's throw pictures: Land of the Sky bones.")).toBeVisible();
  await expect(l.getByText("removed the troupe's throw pictures.")).toBeVisible();
});

test("a player chooses a troupe's own throw pictures in Settings, and the Throws tab shows them (#671)", async ({ browser }) => {
  const custodian = await person(browser, "throwpick-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "throwpick-lead");
  const player = await person(browser, "throwpick-play");
  const headers = { "X-Horatio": "1" };
  await custodian.page.reload();
  const pebbleName = `Pebble Court ${run}`;
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: pebbleName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  // The player plays in it, here as one of its narrators.
  const staffed = await lead.page.request.put(`/api/troupes/${troupeId}/staff`, { headers, data: { handle: player.handle, role: "narrator" } });
  expect(staffed.status(), await staffed.text()).toBe(200);
  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

  const p = player.page;
  await p.getByLabel("Name").fill("Ottilie");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const id = new URL(p.url()).pathname.split("/")[2]!;

  // Until the troupe has all three, only Horatio's are offered.
  await p.goto("/account/settings");
  const choice = p.getByRole("radiogroup", { name: "Throw pictures" });
  await expect(choice.getByRole("radio")).toHaveCount(1);
  await expect(choice.getByRole("radio", { name: /Horatio's/ })).toHaveAttribute("aria-checked", "true");
  for (const which of ["rock", "paper", "scissors"]) {
    const sent = await lead.page.request.post(`/api/troupes/${troupeId}/throw-images/${which}`, { headers, multipart: { file: { name: `${which}.png`, mimeType: "image/png", buffer: png } } });
    expect(sent.status(), await sent.text()).toBe(200);
  }
  await p.reload();
  const pebbles = choice.getByRole("radio", { name: new RegExp(pebbleName) });
  await pebbles.click();
  await expect(p.getByText(`Throw pictures: ${pebbleName}. Saved.`)).toBeVisible();
  await expect(pebbles).toHaveAttribute("aria-checked", "true");

  // The Throws tab throws with the troupe's pictures, read in to keep for no signal.
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Throws" }).click();
  const throws = p.getByRole("region", { name: "Throws" });
  await throws.getByRole("button", { name: "Throw" }).click();
  const face = throws.getByRole("img", { name: /^(Rock|Paper|Scissors)$/ });
  await expect(face).toBeVisible();
  await expect(face.locator("img")).toHaveAttribute("src", /^data:image\/webp;base64,/);
  await p.screenshot({ ...shots("throws-troupe-pictures"), animations: "disabled" });

  // Back to Horatio's own.
  await p.goto("/account/settings");
  await choice.getByRole("radio", { name: /Horatio's/ }).click();
  await expect(p.getByText("Throw pictures: Horatio's. Saved.")).toBeVisible();
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Throws" }).click();
  await throws.getByRole("button", { name: "Throw" }).click();
  await expect(face).toBeVisible();
  await expect(face.locator("img")).toHaveCount(0);
});

test("throwing by flipping the phone face down and back up, on a phone, and switching it off (#669)", async ({ browser }) => {
  test.skip(test.info().project.name !== "phone", "the phone's orientation sensor");
  const { page: p } = await person(browser, "phone-flipper");
  await p.getByLabel("Name").fill("Lisandra");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const id = new URL(p.url()).pathname.split("/")[2]!;
  /** Readings from the orientation sensor, as the phone sends them: beta front to back, gamma side to side. */
  const orient = (betas: number[]) =>
    p.evaluate((bs) => {
      for (const beta of bs) window.dispatchEvent(new DeviceOrientationEvent("deviceorientation", { beta, gamma: 0, alpha: 0 }));
    }, betas);
  const flip = [0, 60, 120, 180, 170, 120, 60, 0];

  // Hold the sheet back until the switch shows: the Play View remakes the Throws tab when it
  // arrives, and the switch must stay without waiting for another reading (#837).
  let sheet!: () => void;
  const held = new Promise<void>((done) => (sheet = done));
  await p.route(`**/api/characters/${id}/play`, async (route) => {
    await held;
    await route.continue();
  });
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Throws" }).click();
  const throws = p.getByRole("region", { name: "Throws" });
  await expect(throws.getByRole("button", { name: "Throw" })).toBeVisible();
  // Offered once the sensor reads, on unless turned off.
  await orient([0]);
  const flipping = throws.getByRole("checkbox", { name: "Throw by flipping" });
  await expect(flipping).toBeChecked();
  sheet();
  await expect(p.getByRole("button", { name: /^Blood \d+ of \d+: open the Tracker$/ })).toBeVisible();
  await p.unroute(`**/api/characters/${id}/play`);
  await expect(flipping).toBeChecked();
  await expect(throws).toContainText("Flip the phone face down and back up to throw.");

  // A flip throws: as the screen comes back up it counts in, as the button does (#756).
  await orient(flip);
  await expect(throws.getByText(/^(Rock|Paper|Scissors)…$/)).toBeVisible();
  await expect(throws.getByRole("img", { name: /^(Rock|Paper|Scissors)$/ })).toBeVisible();
  const past = throws.getByRole("region", { name: "Last throws" }).getByRole("listitem");
  await expect(past).toHaveCount(1);
  // Tilting it to read isn't a flip.
  await orient([0, 40, 90, 120, 90, 40, 0]);
  await p.waitForTimeout(1500);
  await expect(past).toHaveCount(1);

  // Switched off, flips throw nothing, and it stays off on this phone.
  await flipping.uncheck();
  await orient(flip);
  await p.waitForTimeout(300);
  await expect(past).toHaveCount(1);
  await p.goto("/account/settings");
  await expect(p.getByRole("checkbox", { name: "Throw by flipping" })).not.toBeChecked();
});

test("throwing a pool from the Pools tab: the overbid, a tie on pools, a Willpower retest from the tracker and their overbid (#698)", async ({ browser }) => {
  const { page: p } = await person(browser, "pool-thrower");
  const id = await builtVampire(p, "Ferrante", "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]], disciplines: [["Potence", 2], ["Celerity", 1], ["Presence", 1]] });
  await p.goto(`/play/characters/${id}?tab=pools`);
  const dodge = p.getByRole("main").getByRole("listitem").filter({ hasText: /^Dodge/ }).first();
  await expect(dodge).toBeVisible();
  const pool = Number(await dodge.locator("strong").first().textContent());

  // Throw takes Dodge to the Throws tab, defending; their pool is double, so they can overbid.
  await dodge.getByRole("button", { name: "Throw Dodge" }).click();
  await expect(p.getByRole("tab", { name: "Throws" })).toHaveAttribute("aria-selected", "true");
  const challenge = p.getByRole("region", { name: "Challenge" });
  await expect(challenge).toContainText("Throwing Dodge");
  await expect(challenge.getByRole("button", { name: "You defend" })).toHaveAttribute("aria-pressed", "true");
  await challenge.getByLabel("Their pool").fill(String(pool * 2));
  await expect(challenge).toContainText("They can overbid: their pool is at least double yours");
  await expect(challenge).toContainText(`A tie goes to them: their ${pool * 2} is greater than your ${pool}.`);

  const throws = p.getByRole("region", { name: "Throws" });
  const thrown = /^(Rock|Paper|Scissors)$/;
  const beaten: Record<string, string> = { Rock: "Scissors", Paper: "Rock", Scissors: "Paper" };
  const beats: Record<string, string> = { Rock: "Paper", Paper: "Scissors", Scissors: "Rock" };
  /** Throws, then taps what the other side showed: the same, one this throw beats, or one that beats it. */
  const throwAgainst = async (theirs: "same" | "beaten" | "beats") => {
    await throws.getByRole("button", { name: "Throw", exact: true }).click();
    const mine = (await throws.getByRole("img", { name: thrown }).getAttribute("aria-label"))!;
    const shown = theirs === "same" ? mine : theirs === "beaten" ? beaten[mine]! : beats[mine]!;
    await throws.getByRole("button", { name: `They showed ${shown}` }).click();
  };
  const result = throws.getByRole("region", { name: "Tests and retests" }).getByRole("status");

  // A tie goes to the greater pool: theirs.
  await throwAgainst("same");
  await expect(result).toContainText("You lose: their action succeeds");
  await expect(result).toContainText("So far");

  // Willpower for the retest comes off the tracker, and the challenge waits through a look at it.
  await throws.getByRole("button", { name: /^Spend 1 Willpower to retest/ }).click();
  await expect(throws.getByText("Retest with Willpower: throw again.")).toBeVisible();
  await p.getByRole("tab", { name: "Tracker" }).click();
  await expect(p.getByLabel(/^Willpower: \d+ of \d+$/)).toBeVisible();
  const [left, most] = ((await p.getByLabel(/^Willpower: \d+ of \d+$/).getAttribute("aria-label"))!.match(/\d+/g) ?? []).map(Number);
  expect(left).toBe(most! - 1);
  await p.getByRole("tab", { name: "Throws" }).click();
  await expect(throws.getByText("Retest with Willpower: throw again.")).toBeVisible();

  // Won outright on the retest; then their overbid's free retest, which they win: it stands.
  await throwAgainst("beaten");
  await expect(result).toContainText("You win: their action fails");
  await throws.getByRole("button", { name: "Their overbid retest" }).click();
  await throwAgainst("beats");
  await expect(result).toContainText("You lose: their action succeeds");
  await expect(result).not.toContainText("exceptional");
  await expect(result).toContainText("This stands");
  await expect(throws.getByRole("list", { name: "Tests" }).getByRole("listitem")).toHaveCount(3);
  await p.screenshot({ ...shots("throws-pool"), animations: "disabled" });
});

test("Shape of the Beast on the Play View: a Huge fight form adds Healthy levels and Brawl, flight form ends it, and the Scene shows it", async ({ browser }) => {
  const custodian = await person(browser, "beast-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "beast-lead");
  const troupeName = `Hollow Hill ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC with Shape of the Beast: Physical 5, Brawl 3, Dodge 2, Protean 4, Celerity 2.
  const p = lead.page;
  await (await topBar(p)).getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Ursa", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  for (const [category, name, rating] of [
    ["clan", "Gangrel", null],
    ["attributes", "Physical", 5],
    ["attributes", "Mental", 3],
    ["skills", "Brawl", 3],
    ["skills", "Dodge", 2],
    ["disciplines", "Protean", 4],
    ["disciplines", "Celerity", 2],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category, name, rating, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
  }

  // On the sheet, under Protean: the fight form is a bear with the Huge template.
  await p.goto(`/characters/${npc}/sheet`);
  const choices = p.getByLabel("Shape of the Beast choices");
  await expect(choices).toContainText("flight form bat · fight form wolf · fight form template none");
  await choices.getByRole("button", { name: "choose" }).click();
  await choices.getByLabel("Fight form", { exact: true }).fill("bear");
  await choices.getByLabel("Fight form template").selectOption("Huge");
  await choices.getByRole("button", { name: "Save" }).click();
  await expect(choices).toContainText("fight form bear · fight form template Huge");

  // The Pools tab lists the forms and powers, all off.
  await p.goto(`/play/characters/${npc}?tab=pools`);
  await expect(p.getByRole("heading", { name: "Ursa" })).toBeVisible();
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  const fight = p.getByLabel("Shape of the Beast: fight form (bear, Huge) on");
  const flight = p.getByLabel("Shape of the Beast: flight form (bat) on");
  await expect(fight).not.toBeChecked();
  const unarmed = p.getByRole("listitem").filter({ hasText: /^Unarmed attack/ });
  await expect(unarmed.getByText("8", { exact: true })).toBeVisible();
  await expect(unarmed.getByText("Damage 1 (unarmed) · exceptional 2")).toBeVisible();

  // Into the fight form: Brawl +2 with the reason, aggravated, and Feral Claws alongside.
  await fight.check();
  await expect(unarmed.getByText("10", { exact: true })).toBeVisible();
  await expect(unarmed).toContainText("Physical 5 + Brawl 3 + Shape of the Beast 2");
  await expect(unarmed.getByText("Damage 1 (unarmed), aggravated by Shape of the Beast · exceptional 2")).toBeVisible();
  await p.getByLabel("Feral Claws on").check();
  await expect(fight).toBeChecked();
  await expect(p.getByRole("region", { name: "Switched on now" })).toContainText("In Shape of the Beast: fight form (bear, Huge)");
  await expect(p.getByRole("region", { name: "Switched on now" })).toContainText("On: Feral Claws");
  // Celerity goes with a form too.
  await p.getByLabel("Celerity on").check();
  const initiative = p.getByRole("listitem").filter({ hasText: /^Initiative/ });
  await expect(initiative).toContainText("Physical 5 + Alacrity 2");
  await p.screenshot(shots("play-forms"));

  // The health tracker has two more Healthy boxes, marked from the form; five damage reach into them.
  await p.getByRole("tab", { name: "Tracker" }).click();
  await p.getByLabel("Quick notes").uncheck();
  await expect(p.getByText("+2 Healthy from Shape of the Beast: fight form (bear, Huge)")).toBeVisible();
  await expect(p.getByLabel("unmarked, from the form")).toHaveCount(2);
  for (let i = 0; i < 5; i++) await p.getByRole("button", { name: "+ Normal" }).click();
  await expect(p.getByLabel("normal damage")).toHaveCount(5);
  await expect(p.getByLabel("normal damage, from the form")).toHaveCount(2);

  // Flight form ends the fight form: its levels go with the damage in them.
  await p.getByRole("tab", { name: "Pools" }).click();
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  await flight.check();
  await expect(fight).not.toBeChecked();
  await expect(p.getByLabel("Feral Claws on")).toBeChecked();
  await expect(unarmed.getByText("6", { exact: true })).toBeVisible();
  await expect(unarmed).toContainText("Physical (flight form) 3 + Brawl 3");
  await p.getByRole("tab", { name: "Tracker" }).click();
  await expect(p.getByLabel("normal damage")).toHaveCount(3);
  await expect(
    p.getByText("Turned into Shape of the Beast: flight form (bat): out of Shape of the Beast: fight form (bear, Huge), 2 damage in its levels gone"),
  ).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // Undo puts the fight form back, with its damage; the Scene view on another page shows it as a badge.
  await (await undoInHeader(p, /Turned into Shape of the Beast: flight form/)).click();
  await expect(p.getByLabel("normal damage")).toHaveCount(5);
  await expect(p.getByRole("status")).toHaveText("Saved");
  const scene = await p.context().newPage();
  await openScene(scene, troupeId, "Ursa's den");
  await scene.getByRole("combobox", { name: "Add to the scene" }).fill("Ursa");
  await scene.getByRole("option", { name: /Ursa/ }).click();
  await expect(scene.getByRole("article", { name: "Ursa" }).getByText("Shape of the Beast: fight form (bear, Huge)")).toBeVisible();
  await expect(scene.getByRole("article", { name: "Ursa" }).getByLabel("Health: 5 of 11 marked")).toBeVisible();
  await scene.close();

  // Reset for the next game turns every form and power off.
  await p.getByRole("button", { name: "Reset for next game…" }).click();
  await p.getByRole("button", { name: "Reset for next game", exact: true }).click();
  await expect(p.getByText("Game 2")).toBeVisible();
  await expect(p.getByRole("region", { name: "Switched on now" })).toHaveCount(0);
  await p.getByRole("tab", { name: "Pools" }).click();
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  await expect(fight).not.toBeChecked();
  await expect(p.getByLabel("Celerity on")).not.toBeChecked();
});

test("Ravenous Conglomeration on the Play View: two forms at once, never two of one power, and a third ends the first (#597)", async ({ browser }) => {
  const custodian = await person(browser, "ravenous-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "ravenous-lead");
  const troupeName = `Gorge Hall ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC with Vicissitude 5 (Horrid Form, Blood Form), Protean 4 (Shape of the Beast's two forms) and the luminary power.
  const p = lead.page;
  await (await topBar(p)).getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Zelimir", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  for (const [category, name, rating] of [
    ["clan", "Tzimisce", null],
    ["attributes", "Physical", 5],
    ["attributes", "Mental", 3],
    ["skills", "Brawl", 3],
    ["disciplines", "Vicissitude", 5],
    ["disciplines", "Protean", 4],
    ["luminary_disciplines", "Vicissitude: Ravenous Conglomeration", 1],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category, name, rating, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
  }

  await p.goto(`/play/characters/${npc}?tab=pools`);
  await expect(p.getByRole("heading", { name: "Zelimir" })).toBeVisible();
  // Its Use spends the 4 Blood that starts any number of forms at once.
  await expect(p.getByRole("button", { name: "Use Vicissitude: Ravenous Conglomeration, 4 Blood" })).toBeVisible();

  const switches = p.getByRole("button", { name: "Forms, powers and modifiers" });
  await switches.click();
  await expect(p.getByText(/^Forms: two at once with Ravenous Conglomeration \(Vol\. 2 p\. 249\)/)).toBeVisible();
  const horrid = p.getByLabel("Horrid Form on");
  const fight = p.getByLabel("Shape of the Beast: fight form (wolf) on");
  const flight = p.getByLabel("Shape of the Beast: flight form (bat) on");
  const bloodForm = p.getByLabel("Blood Form on");

  // Horrid Form and the wolf together: both forms' Brawl bonuses count.
  await horrid.check();
  await fight.check();
  await expect(horrid).toBeChecked();
  const banner = p.getByRole("region", { name: "Switched on now" });
  await expect(banner).toContainText("In Horrid Form");
  await expect(banner).toContainText("In Shape of the Beast: fight form (wolf)");
  const unarmed = p.getByRole("listitem").filter({ hasText: /^Unarmed attack/ });
  await expect(unarmed).toContainText("Horrid Form 3");
  await expect(unarmed).toContainText("Shape of the Beast 2");

  // The bat is Shape of the Beast too, so it takes the wolf's place; Horrid Form stays.
  await flight.check();
  await expect(fight).not.toBeChecked();
  await expect(horrid).toBeChecked();
  // A third form ends the one on longest: Horrid Form.
  await bloodForm.check();
  await expect(horrid).not.toBeChecked();
  await expect(flight).toBeChecked();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // The server keeps the order: after a reload, Horrid Form ends the bat, on before Blood Form.
  await p.reload();
  await switches.click();
  await expect(bloodForm).toBeChecked();
  await horrid.check();
  await expect(flight).not.toBeChecked();
  await expect(bloodForm).toBeChecked();
  await p.getByRole("tab", { name: "Tracker" }).click();
  await expect(p.getByText("Turned into Horrid Form: out of Shape of the Beast: flight form (bat)")).toBeVisible();
  await expect(p.getByText("Turned into Blood Form: out of Horrid Form")).toBeVisible();
  await expect(p.getByText("Turned into Shape of the Beast: flight form (bat): out of Shape of the Beast: fight form (wolf)")).toBeVisible();
});

/**
 * Stand-ins for what feeding's finish uses, so a test can see it happen: the
 * sound (oscillators made), a vibration and a notification, granted.
 */
async function watchFeeding(page: Page) {
  await page.context().addInitScript(() => {
    const seen = { sounds: 0, buzzes: 0, notes: [] as string[] };
    (window as unknown as { seen: typeof seen }).seen = seen;
    const Audio = window.AudioContext;
    if (Audio) {
      const make = Audio.prototype.createOscillator;
      Audio.prototype.createOscillator = function () {
        seen.sounds++;
        return make.call(this);
      };
    }
    Object.defineProperty(navigator, "vibrate", { value: () => ((seen.buzzes++), true), configurable: true });
    class Note {
      static permission = "granted";
      static requestPermission = async () => "granted";
      constructor(title: string) {
        seen.notes.push(title);
      }
    }
    Object.defineProperty(window, "Notification", { value: Note, configurable: true, writable: true });
  });
}

const seen = (page: Page) => page.evaluate(() => (window as unknown as { seen: { sounds: number; buzzes: number; notes: string[] } }).seen);

test("Feed on the Play View: 15 minutes for 2 Blood, kept through a reload, cancelled, and capped at the most", async ({ browser }) => {
  const { page } = await person(browser, "feed-player");
  await watchFeeding(page);
  await page.clock.install();
  await page.getByLabel("Name").fill("Ottilie");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  const characterId = new URL(page.url()).pathname.split("/")[2]!;

  // No Herd: 10 Blood, 3 spent.
  await page.goto(`/play/characters/${characterId}`);
  await page.getByLabel("Quick notes").uncheck();
  for (let i = 0; i < 3; i++) await page.getByRole("button", { name: "Spend Blood", exact: true }).last().click();
  await expect(page.getByLabel("Blood: 7 of 10")).toBeVisible();

  // The sheet says what will happen; its Cancel changes nothing.
  await page.getByRole("button", { name: "Feed", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Feed" });
  await expect(sheet).toContainText("Feed — 15 minutes, +2 Blood.");
  await expect(sheet).toContainText("+2 Blood: Blood 7 → 9");
  await expect(sheet).toContainText("Tell a storyteller or narrator you're feeding first.");
  await expect(sheet).toContainText("core p. 294");
  await expect(sheet.getByRole("radio")).toHaveCount(0);
  await page.screenshot(shots("feed-sheet"));
  await sheet.getByRole("button", { name: "Cancel" }).click();
  await expect(sheet).toHaveCount(0);

  // Started, it counts down, and a reload keeps the time.
  await page.getByRole("button", { name: "Feed", exact: true }).click();
  await sheet.getByRole("button", { name: "Start" }).click();
  const timer = page.getByRole("dialog", { name: "Feeding" });
  await expect(timer.getByRole("timer")).toHaveText(/^(15:00|14:5\d)$/);
  await page.clock.fastForward("05:00");
  await expect(timer.getByRole("timer")).toHaveText(/^(10:00|09:5\d)$/);
  await page.reload();
  await expect(timer.getByRole("timer")).toHaveText(/^(10:00|09:5\d)$/);
  await page.screenshot(shots("feed-timer"));

  // Cancel stops it and changes nothing, even after a reload.
  await timer.getByRole("button", { name: "Cancel" }).click();
  await expect(timer).toHaveCount(0);
  await expect(page.getByLabel("Blood: 7 of 10")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Blood: 7 of 10")).toBeVisible();
  await expect(timer).toHaveCount(0);
  await expect(page.getByText("“Fed”")).toHaveCount(0);

  // The whole 15 minutes: blood rises, a sound and a buzz, and +2 Blood.
  await page.getByRole("button", { name: "Feed", exact: true }).click();
  await sheet.getByRole("button", { name: "Start" }).click();
  await page.clock.fastForward("15:00");
  const fed = page.getByRole("dialog", { name: "You fed" });
  await expect(fed).toContainText("You fed.+2 Blood (hunted): Blood 7 → 9.");
  await expect(fed.getByTestId("feed-fill")).toHaveAttribute("data-motion", "fill");
  expect((await seen(page)).sounds).toBeGreaterThan(0);
  expect((await seen(page)).buzzes).toBe(1);
  await page.waitForTimeout(2000);
  await page.screenshot(shots("feed-done"));
  await fed.getByRole("button", { name: "Done" }).click();
  await expect(fed).toHaveCount(0);
  await expect(page.getByLabel("Blood: 9 of 10")).toBeVisible();
  await expect(page.getByText("Blood 7 → 9")).toBeVisible();
  await expect(page.getByText("“Fed (hunted)”")).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Saved");

  // Turned off on the timer, the sound stays off. Blood can't go above the most.
  await page.getByRole("button", { name: "Feed", exact: true }).click();
  await sheet.getByRole("button", { name: "Start" }).click();
  await timer.getByLabel("Sound").uncheck();
  await page.reload();
  await expect(timer.getByLabel("Sound")).not.toBeChecked();
  await page.clock.fastForward("15:00");
  await expect(fed).toContainText("+1 Blood (hunted), now full: Blood 9 → 10.");
  expect((await seen(page)).sounds).toBe(0); // a fresh page since the reload, and no sound made
  await fed.getByRole("button", { name: "Done" }).click();
  await expect(page.getByLabel("Blood: 10 of 10")).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Saved");
});

/** Hide or show the page, as locking the phone or switching apps does. */
async function setShown(page: Page, shown: boolean) {
  await page.evaluate((shown) => {
    Object.defineProperty(document, "visibilityState", { value: shown ? "visible" : "hidden", configurable: true });
    Object.defineProperty(document, "hidden", { value: !shown, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  }, shown);
}

test("Feed with Herd: 5 minutes for Blood equal to Herd, waiting while the phone is locked, added once, with Undo", async ({ browser }) => {
  const custodian = await person(browser, "feed-custodian");
  makeCustodian(custodian.email);
  // Reduced motion: the finish fades in rather than filling the screen.
  const lead = await person(browser, "feed-lead", { reducedMotion: "reduce" });
  const troupeName = `Court of Thirst ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC with Herd 3, played by the lead: staff start Feed for a character too.
  const p = lead.page;
  await watchFeeding(p);
  await p.clock.install();
  await (await topBar(p)).getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Benedek", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category: "backgrounds", name: "Herd", rating: 3, detail: "" } });
  expect(rated.status(), await rated.text()).toBe(200);

  await p.goto(`/play/characters/${npc}`);
  await p.getByLabel("Quick notes").uncheck();
  for (let i = 0; i < 4; i++) await p.getByRole("button", { name: "Spend Blood", exact: true }).last().click();
  await expect(p.getByLabel("Blood: 6 of 10")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  await p.getByRole("button", { name: "Feed", exact: true }).click();
  const sheet = p.getByRole("dialog", { name: "Feed" });
  // Both feeds are offered, the Herd one chosen to start with, each saying what it gives.
  await expect(sheet.getByRole("radio")).toHaveCount(2);
  await expect(sheet.getByRole("radio", { name: /Feed from your Herd: 5 minutes, \+3 Blood \(Herd 3\)/ })).toBeChecked();
  await expect(sheet.getByRole("radio", { name: /Hunt: 15 minutes, \+2 Blood/ })).not.toBeChecked();
  await expect(sheet).toContainText("+3 Blood: Blood 6 → 9");
  await expect(sheet).toContainText("+2 Blood: Blood 6 → 8");
  await expect(sheet).toContainText("Your Herd is quicker and gives more");
  await expect(sheet).toContainText("core pp. 102–103");
  await sheet.getByRole("button", { name: "Start" }).click();
  const timer = p.getByRole("dialog", { name: "Feeding" });
  await expect(timer.getByRole("timer")).toHaveText(/^(05:00|04:5\d)$/);

  // The phone locked for two minutes: the time is still right when it is back.
  await setShown(p, false);
  await p.clock.fastForward("02:00");
  await setShown(p, true);
  await expect(timer.getByRole("timer")).toHaveText(/^(03:00|02:5\d)$/);

  // Locked when the time is up: a notification, and the Blood waits.
  await setShown(p, false);
  await p.clock.fastForward("03:00");
  await expect.poll(async () => (await seen(p)).notes).toEqual(["Feeding is done"]);
  await expect(timer.getByRole("timer")).toHaveText("00:00");
  const fed = p.getByRole("dialog", { name: "You fed" });
  await expect(fed).toHaveCount(0);
  const blood = async () => (await (await p.request.get(`/api/characters/${npc}/play`)).json()).blood.value;
  expect(await blood()).toBe(6);

  // Back to the page: the result, faded in, and the Blood added.
  await setShown(p, true);
  await expect(fed).toContainText("You fed.+3 Blood (Herd 3): Blood 6 → 9.");
  await expect(fed.getByTestId("feed-fill")).toHaveAttribute("data-motion", "fade");
  await p.screenshot(shots("feed-done-reduced-motion"));
  // Never twice: a reload shows the same result, and other devices see it once.
  await expect.poll(blood).toBe(9);
  await p.reload();
  await expect(fed).toContainText("+3 Blood (Herd 3): Blood 6 → 9.");
  await p.waitForTimeout(500);
  expect(await blood()).toBe(9);
  const log = (await (await p.request.get(`/api/characters/${npc}/play`)).json()).log as { note: string }[];
  expect(log.filter((e) => e.note === "Fed (Herd 3)")).toHaveLength(1);

  // Undo takes it back, as any tap.
  await fed.getByRole("button", { name: "Undo" }).click();
  await expect(fed).toHaveCount(0);
  await expect(p.getByLabel("Blood: 6 of 10")).toBeVisible();
  await expect(p.getByText("Undid: Blood 6 → 9")).toBeVisible();
  await expect.poll(blood).toBe(6);

  // With Herd 1 the hunt is chosen to start with, and taking it gives +2 after 15 minutes.
  const lowered = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category: "backgrounds", name: "Herd", rating: 1, detail: "" } });
  expect(lowered.status(), await lowered.text()).toBe(200);
  await p.reload();
  await p.getByRole("button", { name: "Feed", exact: true }).click();
  await expect(sheet.getByRole("radio", { name: /Hunt: 15 minutes, \+2 Blood/ })).toBeChecked();
  await expect(sheet.getByRole("radio", { name: /Feed from your Herd: 5 minutes, \+1 Blood \(Herd 1\)/ })).not.toBeChecked();
  await expect(sheet).toContainText("Your Herd is quicker, but hunting gives more Blood");
  await sheet.getByRole("button", { name: "Start" }).click();
  await expect(timer.getByRole("timer")).toHaveText(/^(15:00|14:5\d)$/);
  await expect(timer).toContainText("Hunting");
  await p.clock.fastForward("15:00");
  await expect(fed).toContainText("You fed.+2 Blood (hunted): Blood 6 → 8.");
  await expect.poll(blood).toBe(8);
  const hunted = (await (await p.request.get(`/api/characters/${npc}/play`)).json()).log as { note: string }[];
  expect(hunted.filter((e) => e.note === "Fed (hunted)")).toHaveLength(1);
});

test("Derangement traits on the Play View: a temporary derangement added, warnings to the edge, kept through Reset, and removed", async ({ browser }) => {
  const custodian = await person(browser, "derange-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "derange-lead");
  const troupeName = `Court of Bedlam ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Two NPCs the lead runs, neither with the Derangement flaw: a Malkavian, whose
  // clan weakness is a derangement, and a Toreador.
  const p = lead.page;
  await (await topBar(p)).getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const npc = async (name: string, clan: string) => {
    const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(made.status(), await made.text()).toBe(201);
    const id: string = (await made.json()).id;
    const rated = await p.request.put(`/api/characters/${id}/npc/ratings`, { headers, data: { category: "clan", name: clan, rating: null, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
    return id;
  };
  const ophelia = await npc("Ophelia", "Malkavian");
  const lucien = await npc("Lucien", "Toreador");

  // No Derangement flaw on the sheet: no tracker, only a way to add one.
  await p.goto(`/play/characters/${lucien}`);
  await expect(p.getByLabel("Blood: 10 of 10")).toBeVisible();
  await expect(p.getByRole("heading", { name: "Derangement traits" })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Add a temporary derangement…" })).toBeVisible();

  // The Malkavian's clan derangement is added by hand, as a temporary one.
  await p.goto(`/play/characters/${ophelia}`);
  await p.getByLabel("Quick notes").uncheck();
  await expect(p.getByRole("heading", { name: "Derangement traits" })).toHaveCount(0);
  await p.getByRole("button", { name: "Add a temporary derangement…" }).click();
  const adding = p.getByRole("dialog", { name: "Temporary derangement" });
  await adding.getByLabel("Derangement").fill("Paranoia: the Prince");
  await adding.getByLabel("Where it came from (optional)").fill("Malkavian clan weakness");
  await adding.getByRole("button", { name: "Add" }).click();
  await expect(p.getByText("Temporary derangement added: Paranoia: the Prince, from Malkavian clan weakness")).toBeVisible();

  // A Malkavian always has 1, so it can't be removed.
  const traits = p.getByRole("region", { name: "Derangement traits" });
  await expect(traits.getByLabel("Derangement traits: 1 of 3")).toBeVisible();
  await expect(traits).toContainText("Malkavians always have 1.");
  await expect(traits.getByRole("listitem").filter({ hasText: "Paranoia: the Prince" })).toContainText("Temporary, from Malkavian clan weakness");
  await expect(traits.getByRole("button", { name: "Remove a Derangement trait", exact: true }).last()).toBeDisabled();
  await expect(traits.getByRole("button", { name: "Severe response" })).toBeDisabled();

  // Two triggers resisted: a warning at 2, and at 3 how a psychotic break plays out.
  const mark = traits.getByRole("button", { name: "Mark a Derangement trait", exact: true }).last();
  await mark.click();
  await expect(traits.getByRole("note", { name: "One trait from the edge" })).toContainText("MET: VtM core, p. 267");
  await mark.click();
  await expect(traits.getByLabel("Derangement traits: 3 of 3")).toBeVisible();
  const edge = traits.getByRole("note", { name: "On the edge of a psychotic break" });
  await expect(edge).toContainText("A severe response lasts five minutes.");
  await expect(edge).toContainText("to 1, as a Malkavian always keeps 1");
  // A warning only: the tap goes through, and nothing is blocked.
  await expect(p.getByText("Derangement traits 2 → 3")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await p.screenshot(shots("play-derangements"));
  // Undo takes one back, as any tap.
  await (await undoInHeader(p, "Derangement traits 2 → 3")).click();
  await expect(p.getByText("Undid: Derangement traits 2 → 3")).toBeVisible();
  await expect(traits.getByLabel("Derangement traits: 2 of 3")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // Another device (the custodian's) sees the same.
  const other = custodian.page;
  await other.goto(`/play/characters/${ophelia}`);
  await expect(other.getByLabel("Derangement traits: 2 of 3")).toBeVisible();
  await expect(other.getByText("Paranoia: the Prince", { exact: true })).toBeVisible();

  // Reset for the next game puts Blood back but leaves Derangement traits and the derangement.
  await p.getByRole("button", { name: "Spend Blood", exact: true }).last().click();
  await expect(p.getByLabel("Blood: 9 of 10")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await p.getByRole("button", { name: "Reset for next game…" }).click();
  await expect(p.getByText("Derangement traits stay at 2.")).toBeVisible();
  await p.getByRole("button", { name: "Reset for next game", exact: true }).click();
  await expect(p.getByText("Game 2")).toBeVisible();
  await expect(p.getByLabel("Blood: 10 of 10")).toBeVisible();
  await expect(traits.getByLabel("Derangement traits: 2 of 3")).toBeVisible();
  await p.reload();
  await expect(traits.getByLabel("Derangement traits: 2 of 3")).toBeVisible();
  await expect(traits.getByText("Paranoia: the Prince", { exact: true })).toBeVisible();

  // A severe response clears them, down to the Malkavian's 1.
  await traits.getByRole("button", { name: "Severe response" }).click();
  await expect(traits.getByLabel("Derangement traits: 1 of 3")).toBeVisible();
  await expect(p.getByText("Derangement traits 2 → 1")).toBeVisible();
  await expect(p.getByText("“Severe response”")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await other.reload();
  await expect(other.getByLabel("Derangement traits: 1 of 3")).toBeVisible();

  // Removed by the player when it's over: the tracker goes, back to a way to add one.
  await traits.getByRole("button", { name: "Remove Paranoia: the Prince" }).click();
  await expect(p.getByText("Temporary derangement removed: Paranoia: the Prince, from Malkavian clan weakness")).toBeVisible();
  await expect(p.getByRole("heading", { name: "Derangement traits" })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Add a temporary derangement…" })).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await other.reload();
  await expect(other.getByRole("heading", { name: "Derangement traits" })).toHaveCount(0);
});

test("Beast traits on the Play View warn what each one brings, and the Frenzy rules open on request with the player's numbers", async ({ browser }) => {
  const custodian = await person(browser, "frenzy-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "frenzy-lead");
  const troupeName = `Court of Fangs ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // A Brujah NPC the lead runs at game.
  const p = lead.page;
  await (await topBar(p)).getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Tobias", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category: "clan", name: "Brujah", rating: null, detail: "" } });
  expect(rated.status(), await rated.text()).toBe(200);
  const mental = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category: "attributes", name: "Mental", rating: 4, detail: "" } });
  expect(mental.status(), await mental.text()).toBe(200);

  await p.goto(`/play/characters/${npc}`);
  await expect(p.getByLabel("Beast traits: 0 of 5")).toBeVisible();
  await expect(p.getByRole("note")).toHaveCount(0);
  // With no Beast traits, the closed Frenzy panel shows no numbers.
  const frenzyPanel = p.locator("section").filter({ has: p.getByRole("button", { name: /^Frenzy/ }) });
  await expect(frenzyPanel.getByText(/^You: \d+ against \d+$/)).toHaveCount(0);
  const willpower = Number((await p.getByLabel(/^Willpower: \d+ of \d+$/).getAttribute("aria-label"))!.match(/^Willpower: (\d+)/)![1]);

  // Each Beast trait says what now makes a frenzy test, and how to play it.
  const gain = p.getByRole("button", { name: "Gain a Beast traits point" });
  await gain.click();
  const foothold = p.getByRole("note", { name: "The Beast has a foothold" });
  await expect(foothold).toContainText("You can frenzy now.");
  await expect(foothold).toContainText("against 11");
  // Once there is a Beast trait, the player's own numbers show even with the panel closed (issue #371).
  await expect(frenzyPanel.getByText(/^You: \d+ against \d+$/)).toHaveText(`You: ${4 + willpower} against 11`);
  await expect(frenzyPanel).toContainText(`Mental 4 + Willpower ${willpower}, against 10 + Beast traits 1`);
  // They follow Willpower.
  await p.getByRole("button", { name: "Spend Willpower", exact: true }).first().click();
  await expect(frenzyPanel.getByText(/^You: \d+ against \d+$/)).toHaveText(`You: ${3 + willpower} against 11`);
  await p.getByRole("button", { name: "Restore Willpower", exact: true }).first().click();
  await expect(foothold).toContainText("MET: VtM core, pp. 301–302; Vol. II Issue 1 update, pp. 97–98");
  await gain.click();
  await expect(p.getByRole("note", { name: "The Beast is awake" })).toContainText("a single blow of 3 or more damage (rage)");
  await gain.click();
  await gain.click();
  await expect(p.getByLabel("Beast traits: 4 of 5")).toBeVisible();
  await expect(p.getByRole("note", { name: "One trait from losing Humanity" })).toContainText("One more Beast trait costs a dot of permanent Humanity.");
  // A warning only: the fifth goes through.
  await gain.click();
  await expect(p.getByLabel("Beast traits: 5 of 5")).toBeVisible();
  await expect(p.getByRole("note", { name: "A dot of Humanity is lost" })).toBeVisible();
  await expect(p.getByText("Beast traits 4 → 5")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // The Frenzy rules, closed until asked for.
  const frenzy = p.getByRole("button", { name: /^Frenzy/ });
  await expect(frenzy).toHaveAttribute("aria-expanded", "false");
  await expect(p.getByText("Riding the wave")).toHaveCount(0);
  await frenzy.click();
  await expect(frenzy).toHaveAttribute("aria-expanded", "true");
  await expect(p.getByRole("heading", { name: /Riding the wave/ })).toBeVisible();
  await expect(p.getByText("Fear ends once you've escaped and hidden quietly for 10 minutes.", { exact: false })).toBeVisible();
  // Resisting has them too, at five Beast traits.
  await expect(frenzyPanel.getByText(/^You: \d+ against \d+$/)).toHaveText(`You: ${4 + willpower} against 15`);
  await p.screenshot(shots("play-frenzy"));
  await frenzy.click();
  await expect(frenzy).toHaveAttribute("aria-expanded", "false");
  await expect(p.getByText("Riding the wave")).toHaveCount(0);
});
