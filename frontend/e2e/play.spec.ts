import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, openScene, undoInHeader } from "./support";

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

test("at a game, the Play View tracks blood and uses, offline too, and the storytellers reset the troupe", async ({ browser }) => {
  const custodian = await person(browser, "play-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "play-lead");
  const troupeName = `Court of Candles ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC the lead runs at game, made straight through the API: Generation 2 (12
  // blood, 2 a turn), Herd 2, Physical 5, Social 4, Mental 3, Dodge 2, Intimidation 3
  // and Celerity 2.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
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
  await p.goto(`/troupes/${troupeId}/rules/starting`);
  await p.getByRole("button", { name: "Change starting blood" }).click();
  await p.getByLabel("This much:").check();
  await p.getByLabel("Starting blood").fill("8");
  await p.getByRole("button", { name: "Save" }).click();
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

test("Shape of the Beast on the Play View: a Huge fight form adds Healthy levels and Brawl, flight form ends it, and the Scene shows it", async ({ browser }) => {
  const custodian = await person(browser, "beast-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "beast-lead");
  const troupeName = `Hollow Hill ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC with Shape of the Beast: Physical 5, Brawl 3, Dodge 2, Protean 4, Celerity 2.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
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
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC with Herd 3, played by the lead: staff start Feed for a character too.
  const p = lead.page;
  await watchFeeding(p);
  await p.clock.install();
  await p.getByRole("link", { name: "Troupes" }).click();
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
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Two NPCs the lead runs, neither with the Derangement flaw: a Malkavian, whose
  // clan weakness is a derangement, and a Toreador.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
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
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // A Brujah NPC the lead runs at game.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
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
