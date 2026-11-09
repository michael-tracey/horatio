import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, PASSWORD } from "./support";

/** Storytellers building NPCs, of every kind and form. */

closeContextsAfterEach();

test("storytellers build an NPC quickly and give it a title", async ({ browser }) => {
  const custodian = await person(browser, "npc-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "npc-lead");
  const troupeName = `Court of Smoke ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  const created = custodian.page.waitForResponse((r) => r.url().endsWith("/api/troupes") && r.request().method() === "POST");
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  const response = await created;
  expect(response.status(), await response.text()).toBe(201);
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await p.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  // NPCs share the Characters list (#556): it opens on player characters, and shows NPCs at a choice.
  await p.locator("main").getByRole("radio", { name: "NPCs" }).click();
  await expect(p).toHaveURL(/\/characters\?show=npcs$/);
  await p.getByRole("button", { name: "New NPC" }).click();
  await expect(p.getByRole("heading", { name: "New NPC" })).toBeVisible();
  await p.getByLabel("Name").fill("Prince Vasquez");
  await p.getByRole("button", { name: "Quick build" }).click();
  await expect(p.getByRole("heading", { name: "Prince Vasquez" })).toBeVisible();

  await p.getByLabel("Clan", { exact: true }).selectOption("Ventrue");
  await expect(p.getByLabel("Clan", { exact: true })).toHaveValue("Ventrue");
  // A Prince must be Camarilla: a title of a sect goes only to its characters.
  await p.getByLabel("Sect", { exact: true }).selectOption("Camarilla");
  await expect(p.getByLabel("Sect", { exact: true })).toHaveValue("Camarilla");
  // Creation picks are fitted to an NPC built quickly, so its creation dots are free as a
  // player character's are (#527): Social takes the attribute pick at 7, and its eighth
  // dot is bought (attributes: 3 a dot).
  await p.getByRole("button", { name: "Social 8", exact: true }).click();
  await expect(p.getByText("3 XP", { exact: true })).toBeVisible();
  // Each attribute's focus is chosen beside it, one of three; choosing again swaps it.
  await expect(p.getByRole("heading", { name: "Focuses" })).toHaveCount(0);
  await p.getByLabel("Social focus", { exact: true }).selectOption("Charisma");
  await expect(p.getByLabel("Social focus", { exact: true })).toHaveValue("Charisma");
  await p.getByLabel("Social focus", { exact: true }).selectOption("Manipulation");
  await expect(p.getByLabel("Social focus", { exact: true })).toHaveValue("Manipulation");
  await expect(p.getByText("3 XP", { exact: true })).toBeVisible(); // focuses are free
  // The skill pick at 4, and the fifth dot bought: 5 at Generation 1's × 1.
  await p.getByRole("button", { name: "Leadership 5", exact: true }).click();
  await expect(p.getByText("8 XP", { exact: true })).toBeVisible();
  // Morality is one path at one rating: moving to a Path keeps the rating, free.
  await expect(p.getByLabel("Morality", { exact: true })).toHaveValue("Humanity");
  await p.getByRole("button", { name: "Humanity 4", exact: true }).click();
  await expect(p.getByRole("button", { name: "Humanity 4", exact: true })).toHaveAttribute("aria-pressed", "true");
  await p.getByLabel("Morality", { exact: true }).selectOption("Caine");
  await expect(p.getByRole("button", { name: "Caine 4", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(p.getByRole("button", { name: /^Humanity \d+$/ })).toHaveCount(0);
  await expect(p.getByText("8 XP", { exact: true })).toBeVisible();
  await p.screenshot(shots("npc"));

  // Its badge, from the Build tab: the same dialog as a player character's, then printing.
  await p.getByRole("button", { name: "Badge", exact: true }).click();
  await expect(p.getByRole("dialog").getByText("Path of Caine")).toBeVisible();
  const npcBadgeTab = p.context().waitForEvent("page");
  await p.getByRole("dialog").getByRole("button", { name: "Print badge" }).click();
  const npcBadge = await npcBadgeTab;
  await expect(npcBadge.getByRole("article", { name: "Badge for Prince Vasquez" }).getByText("Ventrue · Neonate")).toBeVisible();
  await npcBadge.close();
  await p.getByRole("dialog").getByRole("button", { name: "Close" }).click();

  // Titles are given on the troupe's Characters tab, where Everyone shows NPCs beside player characters.
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await p.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await expect(p.getByText("No player characters have joined this troupe yet.")).toBeVisible();
  await p.locator("main").getByRole("radio", { name: "Everyone" }).click();
  await p.getByRole("button", { name: "Actions for Prince Vasquez" }).click();
  await p.getByRole("menuitem", { name: "Titles…" }).click();
  const titles = p.getByRole("dialog", { name: "Prince Vasquez's titles" });
  await titles.getByLabel("Title").fill("Prince");
  await p.screenshot(shots("give-title"));
  await titles.getByLabel("Title").press("Enter");
  await expect(titles.getByRole("button", { name: "Take the title Prince from Prince Vasquez" })).toBeVisible();
  await titles.getByRole("button", { name: "Close" }).click();
  // The title shows on the row, to read.
  await expect(p.getByRole("list", { name: "Prince Vasquez's titles" }).getByText("Prince")).toBeVisible();
  await p.screenshot(shots("roster-titles"));
  await p.getByRole("link", { name: "Troupe", exact: true }).click();
  await p.locator("main").getByRole("link", { name: "Log", exact: true }).click();
  await expect(p.getByText("npc-lead gave Prince Vasquez the title Prince.")).toBeVisible();

  // The NPCs: badges for those ticked or for every NPC, and each one's Play View. The NPCs
  // tab's old address opens the Characters list on its NPCs.
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const another = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers: { "X-Horatio": "1" }, data: { name: "Sheriff Ilse", wizard: false } });
  expect(another.status(), await another.text()).toBe(201);
  await p.goto(`/troupes/${troupeId}/npcs`);
  await expect(p).toHaveURL(new RegExp(`/troupes/${troupeId}/characters\\?show=npcs$`));
  await expect(p.locator("main").getByRole("radio", { name: "NPCs" })).toHaveAttribute("aria-checked", "true");
  await p.getByLabel("Select Prince Vasquez").check();
  await p.getByRole("button", { name: /^Print…/ }).click();
  let badgesTab = p.context().waitForEvent("page");
  await p.getByRole("button", { name: "Badges for selected (1)" }).click();
  let badges = await badgesTab;
  await expect(badges.getByRole("article")).toHaveCount(1);
  await expect(badges.getByRole("article", { name: "Badge for Prince Vasquez" }).getByText("Prince", { exact: true })).toBeVisible();
  await badges.close();
  badgesTab = p.context().waitForEvent("page");
  await p.getByRole("button", { name: "Badges for all 2" }).click();
  badges = await badgesTab;
  await expect(badges.getByRole("article")).toHaveCount(2);
  await expect(badges.getByRole("article", { name: "Badge for Sheriff Ilse" })).toBeVisible();
  await badges.close();
  // Each NPC's actions are behind the same ⋯ as a player character's: Play first, listing it
  // on the Who's Who, and its badge.
  // Listed shows as Yes in its column, or under the name on a phone.
  const listed = p.getByRole("row", { name: "Sheriff Ilse" }).getByText(/^(Yes|On the Who’s Who)$/).filter({ visible: true });
  await expect(listed).toHaveCount(0);
  await p.getByRole("button", { name: "Actions for Sheriff Ilse" }).click();
  await p.getByRole("menuitem", { name: "List on the Who’s Who" }).click();
  await expect(listed).toBeVisible();
  await p.getByRole("button", { name: "Actions for Sheriff Ilse" }).click();
  await p.getByRole("menuitem", { name: "Take off the Who’s Who" }).click();
  await expect(listed).toHaveCount(0);
  await p.getByRole("button", { name: "Actions for Prince Vasquez" }).click();
  await p.getByRole("menuitem", { name: "Badge…" }).click();
  await expect(p.getByRole("dialog", { name: "Prince Vasquez's badge" }).getByText("Path of Caine")).toBeVisible();
  await p.getByRole("dialog").getByRole("button", { name: "Close" }).click();
  await expect(p.getByRole("button", { name: "Actions for Prince Vasquez" })).toBeFocused();
  await p.getByRole("button", { name: "Actions for Sheriff Ilse" }).click();
  await p.screenshot(shots("npcs"));
  await p.getByRole("menuitem", { name: "Play", exact: true }).click();
  await expect(p.getByRole("heading", { name: "Sheriff Ilse" })).toBeVisible();
  await expect(p.getByRole("tab", { name: "Tracker" })).toBeVisible();
});

test("a quick NPC's creation picks are fitted, and staff move one by hand", async ({ browser }) => {
  const custodian = await person(browser, "picks-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "picks-lead");
  const { npcId } = await troupeWithNpc(custodian.page, lead.handle, "Court of Picks", "Corvin Hale");
  const p = lead.page;
  const occult = await p.request.put(`/api/characters/${npcId}/npc/ratings`, { headers: { "X-Horatio": "1" }, data: { category: "skills", name: "Occult", rating: 3 } });
  expect(occult.status(), await occult.text()).toBe(200);
  await p.goto(`/characters/${npcId}`);

  // Fitted for the most XP saved: Brawl 5 takes the pick at 4, Occult 3 the pick at 3;
  // only Brawl's fifth dot is bought. The picks show in the wizard's slots.
  const card = p.getByRole("region", { name: "Skills picks" });
  await expect(p.getByRole("heading", { name: "Creation picks" })).toBeVisible();
  await expect(card.getByRole("combobox", { name: "Skills at 4", exact: true })).toHaveValue("Brawl");
  await expect(card.getByRole("combobox", { name: "Skills at 3, pick 1 of 2" })).toHaveValue("Occult");
  await expect(p.getByText("5 XP", { exact: true })).toBeVisible();
  await expect(p.getByText("by hand", { exact: true })).toHaveCount(0);

  // Its player had Occult at 2 in Yorick: chosen there, it moves, placed by hand, and its third dot is bought.
  const at2 = card.getByRole("combobox", { name: "Skills at 2, pick 1 of 3" });
  await at2.click();
  await p.screenshot(shots("npc-picks-open"));
  await p.getByRole("listbox", { name: "Skills at 2, pick 1 of 3" }).getByRole("option", { name: "Occult (at 3)" }).click();
  await expect(at2).toHaveValue("Occult");
  await expect(card.getByRole("combobox", { name: "Skills at 3, pick 1 of 2" })).toHaveValue("");
  await expect(card.getByText("by hand", { exact: true })).toBeVisible();
  await expect(p.getByText("8 XP", { exact: true })).toBeVisible();
  await p.screenshot(shots("npc-picks"));

  // Clearing a slot takes the pick off its trait, and the fitting leaves it alone.
  await card.getByRole("button", { name: "Take Brawl off" }).click();
  await expect(p.getByText("Kept without a pick: Brawl.")).toBeVisible();
  await expect(card.getByRole("combobox", { name: "Skills at 4", exact: true })).toHaveValue("");

  // Fitting all again forgets both.
  await p.getByRole("button", { name: "Fit all again" }).click();
  await expect(card.getByRole("combobox", { name: "Skills at 4", exact: true })).toHaveValue("Brawl");
  await expect(card.getByRole("combobox", { name: "Skills at 3, pick 1 of 2" })).toHaveValue("Occult");
  await expect(p.getByText("by hand", { exact: true })).toHaveCount(0);
  await expect(p.getByText("5 XP", { exact: true })).toBeVisible();
});

test("a quick NPC's Ventrue Royalty places its free backgrounds, and staff take one off", async ({ browser }) => {
  const custodian = await person(browser, "places-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "places-lead");
  const { npcId } = await troupeWithNpc(custodian.page, lead.handle, "Court of Places", "Aurelia Vane");
  const p = lead.page;
  for (const [category, name, rating] of [
    ["backgrounds", "Resources", 5],
    ["backgrounds", "Haven", 3],
    ["backgrounds", "Allies", 2],
    ["merits", "Ventrue Royalty", 2],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${npcId}/npc/ratings`, { headers: { "X-Horatio": "1" }, data: { category, name, rating } });
    expect(rated.status(), await rated.text()).toBe(200);
  }
  await p.goto(`/characters/${npcId}`);

  // The merit's 4, 3 and 2 are fitted where they save the most (#566): only Resources' fifth
  // dot is bought, beside Brawl's.
  const royalty = p.getByRole("region", { name: "Ventrue Royalty places" });
  await expect(royalty.getByRole("combobox", { name: "Ventrue Royalty at 4", exact: true })).toHaveValue("Resources");
  await expect(royalty.getByRole("combobox", { name: "Ventrue Royalty at 3", exact: true })).toHaveValue("Haven");
  await expect(royalty.getByRole("combobox", { name: "Ventrue Royalty at 2", exact: true })).toHaveValue("Allies");
  await expect(p.getByText("10 XP", { exact: true })).toBeVisible();
  await p.screenshot(shots("npc-places"));

  // Its player had Haven bought, not placed: taken off, Haven takes the creation pick at 3 instead.
  await royalty.getByRole("button", { name: "Take Haven off" }).click();
  await expect(p.getByText("Kept without a merit's free dots: Haven.")).toBeVisible();
  await expect(royalty.getByRole("combobox", { name: "Ventrue Royalty at 3", exact: true })).toHaveValue("");
  await expect(p.getByRole("region", { name: "Backgrounds picks" }).getByRole("combobox", { name: "Backgrounds at 3", exact: true })).toHaveValue("Haven");

  // Fitting all again puts it back.
  await p.getByRole("button", { name: "Fit all again" }).click();
  await expect(royalty.getByRole("combobox", { name: "Ventrue Royalty at 3", exact: true })).toHaveValue("Haven");
  await expect(p.getByText("Kept without a merit's free dots: Haven.")).toHaveCount(0);
});

/** A troupe led by `lead`, made by the custodian, with a sheeted vampire NPC built in it. */
async function troupeWithNpc(custodian: Page, lead: string, troupe: string, npc: string): Promise<{ troupeId: string; npcId: string }> {
  const headers = { "X-Horatio": "1" };
  const made = await custodian.request.post("/api/troupes", { headers, data: { name: `${troupe} ${run}`, lead_handle: lead } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  const built = await custodian.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: npc, wizard: false } });
  expect(built.status(), await built.text()).toBe(201);
  const npcId = (await built.json()).id;
  for (const [category, name, rating] of [
    // Physical and Brawl take creation picks at 5 and 4 (#527); Brawl's fifth dot is bought.
    ["attributes", "Physical", 5],
    ["skills", "Brawl", 5],
  ] as const) {
    const rated = await custodian.request.put(`/api/characters/${npcId}/npc/ratings`, { headers, data: { category, name, rating } });
    expect(rated.status(), await rated.text()).toBe(200);
  }
  return { troupeId, npcId };
}

test("a storyteller gives an NPC to a player, who finds it among their characters", async ({ browser }) => {
  const custodian = await person(browser, "gift-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "gift-lead");
  const heir = await person(browser, "gift-heir");
  const { troupeId, npcId } = await troupeWithNpc(custodian.page, lead.handle, "Court of Gifts", "Odette Lamarr");

  const p = lead.page;
  await p.goto(`/troupes/${troupeId}/npcs`);
  await p.getByRole("button", { name: "Actions for Odette Lamarr" }).click();
  await p.getByRole("menuitem", { name: "Give to a player…" }).click();
  const dialog = p.getByRole("dialog", { name: "Give Odette Lamarr to a player" });
  await dialog.getByLabel("Player").fill(heir.handle);
  await dialog.getByRole("listbox", { name: "People" }).getByRole("option", { name: `@${heir.handle}` }).click();
  await dialog.getByLabel("Unspent XP to carry over").fill("6");
  await dialog.getByLabel("Why").fill("Banked in our old records");
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(dialog.getByText(/^It becomes .*'s character, at home in Court of Gifts/)).toBeVisible();
  await expect(dialog.getByText(/Then 6 XP carried over/)).toBeVisible();
  await p.screenshot(shots("give-npc"));
  await dialog.getByRole("button", { name: `Give Odette Lamarr to @${heir.handle}` }).click();
  await expect(dialog).toBeHidden();
  await expect(p.getByText("No NPCs yet.")).toBeVisible();

  // The player is told, and has it: at home in the troupe, its XP balanced plus what was carried over.
  const h = heir.page;
  await h.reload();
  await expect(h.getByRole("link", { name: /Odette Lamarr/ }).first()).toBeVisible();
  await h.goto(`/characters/${npcId}/xp`);
  await expect(h.getByText("Unspent XP carried over: Banked in our old records")).toBeVisible();
  await expect(h.getByText(/^Imported: what Odette Lamarr's sheet cost/)).toBeVisible();
  const xp = await (await h.request.get(`/api/characters/${npcId}/xp`)).json();
  expect(xp.reduce((sum: number, e: { amount: number }) => sum + e.amount, 0)).toBe(6);
  const character = await (await h.request.get(`/api/characters/${npcId}`)).json();
  expect([character.kind, character.home_troupe_id]).toEqual(["pc", troupeId]);
  const notes = await (await h.request.get("/api/notifications")).json();
  expect(notes.items.map((n: { summary: string }) => n.summary)).toContain(`Odette Lamarr is yours now: Court of Gifts ${run} gave it to you, at home there and accepted`);
});

test("a storyteller exports the troupe's characters and NPCs as a .zip, with emails only if ticked (#567)", async ({ browser }) => {
  const custodian = await person(browser, "export-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "export-lead");
  const { troupeId } = await troupeWithNpc(custodian.page, lead.handle, "Court of Ledgers", "Archivist Bel");

  const p = lead.page;
  await p.goto(`/troupes/${troupeId}/characters?show=npcs`);
  await p.getByRole("button", { name: "More for the troupe's characters" }).click();
  await p.getByRole("menuitem", { name: "Export characters and NPCs…" }).click();
  const dialog = p.getByRole("dialog", { name: "Export characters and NPCs" });
  await dialog.getByRole("radio", { name: "NPCs" }).check();
  await dialog.getByRole("checkbox", { name: "Retainers and Alternate Identities" }).check();
  await expect(dialog.getByRole("checkbox", { name: /Include players' emails/ })).not.toBeChecked();
  await p.screenshot(shots("export-characters"));
  const [download] = await Promise.all([p.waitForEvent("download"), dialog.getByRole("link", { name: "Download .zip" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^court-of-ledgers-\d+-characters-\d{4}-\d{2}-\d{2}\.zip$/);
  const zipped = readFileSync(await download.path());
  // A zip names its files in the clear.
  expect(zipped.subarray(0, 2).toString()).toBe("PK");
  const day = download.suggestedFilename().match(/(\d{4}-\d{2}-\d{2})\.zip$/)![1];
  for (const name of ["manifest.json", `npcs/ArchivistBel-${day}.horatio-character.json`, `sheets/ArchivistBel-${day}.html`]) expect(zipped.includes(name)).toBe(true);
});

test("a storyteller imports the troupe's export, choosing what to do with an NPC already here (#567)", async ({ browser }) => {
  const custodian = await person(browser, "reimport-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "reimport-lead");
  const { troupeId } = await troupeWithNpc(custodian.page, lead.handle, "Court of Returns", "Keeper Anselm");

  const p = lead.page;
  const zip = await p.request.get(`/api/troupes/${troupeId}/character-backups?which=npcs`);
  expect(zip.status()).toBe(200);
  await p.goto(`/troupes/${troupeId}/characters?show=npcs`);
  await p.getByRole("button", { name: "More for the troupe's characters" }).click();
  await p.getByRole("menuitem", { name: "Import characters and NPCs…" }).click();
  await p.getByLabel("Files to import").setInputFiles({ name: "court.zip", mimeType: "application/zip", buffer: await zip.body() });

  // It has the name of the NPC here, so it waits for a choice.
  const anselm = p.getByRole("listitem", { name: "Keeper Anselm" });
  await expect(anselm).toContainText("has this name: skip it, replace it or add a copy.");
  await expect(p.getByRole("button", { name: "Import 0 characters" })).toBeDisabled();
  await anselm.getByRole("radio", { name: "Add a copy" }).check();
  await expect(anselm).toContainText("Comes in as a new NPC of the troupe.");
  await p.getByRole("button", { name: "Import 1 character" }).click();
  await expect(p.getByText("1 new NPC.", { exact: true })).toBeVisible();

  await expect(p.getByRole("link", { name: "Keeper Anselm" })).toBeVisible();
  await p.goto(`/troupes/${troupeId}/characters?show=npcs`);
  await expect(p.getByRole("row", { name: /Keeper Anselm/ })).toHaveCount(2);
});

test("a storyteller sends a claim link, and a newcomer signs up through it and claims the NPC", async ({ browser }) => {
  const custodian = await person(browser, "claim-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "claim-lead");
  const { troupeId, npcId } = await troupeWithNpc(custodian.page, lead.handle, "Court of Claims", "Bastien Roux");

  // From the NPC's own page this time.
  const p = lead.page;
  await p.goto(`/characters/${npcId}`);
  await p.getByRole("button", { name: "More for Bastien Roux" }).click();
  await p.getByRole("menuitem", { name: "Claim link…" }).click();
  const dialog = p.getByRole("dialog", { name: "Claim link for Bastien Roux" });
  await dialog.getByRole("button", { name: "Make a claim link" }).click();
  const url = await dialog.getByLabel("Claim link").inputValue();
  await p.screenshot(shots("claim-link"));
  await dialog.getByRole("button", { name: "Close" }).click();
  await p.goto(`/troupes/${troupeId}/npcs`);
  await expect(p.getByRole("row", { name: /Bastien Roux/ }).getByText("Claim link out")).toBeVisible();

  // Someone with no account opens it, sees whose it is, and signs up to claim it.
  const n = await (await browser.newContext()).newPage();
  await n.goto(new URL(url).pathname);
  await expect(n.getByText("Bastien Roux", { exact: true })).toBeVisible();
  await n.getByRole("link", { name: "Sign up to claim it" }).click();
  await n.getByLabel("Your name").fill("claim-newcomer");
  await n.getByLabel("Handle").fill(`claim-newcomer_${run.slice(-10)}`);
  await n.getByLabel("Email").fill(`claim-newcomer-${run}@example.com`);
  await n.getByLabel("Password").fill(PASSWORD);
  await n.getByRole("button", { name: "Create account" }).click();
  await n.screenshot(shots("claim"));
  await n.getByRole("button", { name: "Claim Bastien Roux" }).click();
  await expect(n.getByRole("heading", { name: "Bastien Roux", level: 1 })).toBeVisible();
  await expect(n).toHaveURL(new RegExp(`/characters/${npcId}`));

  // Used, the link stops working.
  await n.goto(new URL(url).pathname);
  await expect(n.getByText("This claim link has expired or been used. Ask the troupe for a new one.")).toBeVisible();
});

test("storytellers make NPCs of other kinds, sheeted or Stock, and filter the list by kind and form", async ({ browser }) => {
  const custodian = await person(browser, "kinds-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "kinds-lead");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Antlers ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;

  const p = lead.page;
  await p.goto(`/troupes/${troupeId}/characters?show=npcs`);
  await expect(p.getByText("No NPCs yet.")).toBeVisible();
  await p.getByRole("button", { name: "New NPC" }).click();
  await expect(p.getByRole("heading", { name: "New NPC" })).toBeVisible();
  // A Stock werewolf: the kind's resource and pages show as it is picked.
  await p.getByLabel("Name").fill("Bites-the-Hand");
  await p.getByLabel("Kind", { exact: true }).selectOption("werewolf");
  await expect(p.getByText("Supernatural · Rage 10, up to 3 a turn, regains 1 every five turns · pp. 494–495")).toBeVisible();
  await p.getByRole("radio", { name: "Stock" }).click();
  await p.getByLabel("Rating").fill("3");
  await p.getByRole("button", { name: "Make Stock NPC" }).click();
  const wolf = p.getByRole("row", { name: "Bites-the-Hand" });
  // On a phone the kind, form and rating fold in under the name.
  const shows = (row: typeof wolf, text: string | RegExp) => row.getByText(text, { exact: true }).filter({ visible: true });
  await expect(shows(wolf, "Werewolf")).toBeVisible();
  await expect(shows(wolf, "Stock")).toBeVisible();
  await expect(shows(wolf, /^(Rating )?3$/)).toBeVisible();
  // A Stock NPC plays from a Play View of its own.
  // It has no sheet to print, only its badge.
  await p.getByRole("button", { name: "Actions for Bites-the-Hand" }).click();
  await expect(p.getByRole("menuitem", { name: "Play", exact: true })).toBeVisible();
  await expect(p.getByRole("menuitem", { name: "Badge…" })).toBeVisible();
  await expect(p.getByRole("menuitem", { name: "Print sheet" })).toHaveCount(0);
  await p.keyboard.press("Escape");

  // A sheeted mage goes to its quick build, on the Vampire sheet.
  await p.getByLabel("Name").fill("Sarah Juniper");
  await p.getByLabel("Kind", { exact: true }).selectOption("mage");
  await p.getByRole("radio", { name: "Sheeted" }).click();
  await p.getByRole("button", { name: "Quick build" }).click();
  await expect(p.getByRole("heading", { name: "Sarah Juniper" })).toBeVisible();

  await p.goto(`/troupes/${troupeId}/characters?show=npcs`);
  const mage = p.getByRole("row", { name: "Sarah Juniper" });
  await expect(shows(mage, "Mage")).toBeVisible();
  await expect(shows(mage, "Sheeted")).toBeVisible();
  await p.getByRole("button", { name: "Actions for Sarah Juniper" }).click();
  await expect(p.getByRole("menuitem", { name: "Play", exact: true })).toBeVisible();
  await p.keyboard.press("Escape");
  await p.screenshot(shots("npc-kinds"));

  // The filter: by form, then by kind.
  await p.getByLabel("Show form").selectOption("stock");
  await expect(wolf).toBeVisible();
  await expect(mage).toHaveCount(0);
  await p.getByLabel("Show form").selectOption("");
  await p.getByLabel("Show kind").selectOption("mage");
  await expect(mage).toBeVisible();
  await expect(wolf).toHaveCount(0);
  await p.getByLabel("Show form").selectOption("stock");
  await expect(p.getByText("No NPCs of that kind.")).toBeVisible();
  // Kept in the address with the rest.
  await expect(p).toHaveURL(/show=npcs&kind=mage&form=stock$/);
});

test("storytellers build a Stock NPC from the NPCs tab and see the book's stat block", async ({ browser }) => {
  const custodian = await person(browser, "stockb-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "stockb-lead");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Moss ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;

  const p = lead.page;
  await p.goto(`/troupes/${troupeId}/characters?show=npcs`);
  await p.getByRole("button", { name: "New NPC" }).click();
  await p.getByLabel("Name").fill("Gnashes-the-Moon");
  await p.getByLabel("Kind", { exact: true }).selectOption("werewolf");
  await p.getByRole("radio", { name: "Stock" }).click();
  await p.getByLabel("Rating").fill("3");
  await p.getByRole("button", { name: "Make Stock NPC" }).click();
  await p.getByRole("row", { name: "Gnashes-the-Moon" }).getByRole("link", { name: "Gnashes-the-Moon", exact: true }).click();
  await expect(p.getByRole("heading", { name: "Gnashes-the-Moon" })).toBeVisible();

  const add = async (choice: string) => {
    await p.getByLabel("Add a specialisation").selectOption(choice);
    await p.getByRole("button", { name: "Add", exact: true }).click();
  };
  await add("skill:Brawl");
  await add("power:Celerity");
  const block = p.getByRole("list", { name: "Stat block" });
  await expect(block.getByText("Test pool 6 in most challenges")).toBeVisible();
  await expect(block.getByText("Brawl 11")).toBeVisible();
  await expect(block.getByText("Celerity up to 3")).toBeVisible();
  await expect(block.getByText("Rage 10, up to 3 a turn")).toBeVisible();
  await expect(block.getByText("6 health")).toBeVisible();
  await expect(block.getByText("No Willpower: no retests unless it overbids")).toBeVisible();
  await expect(p.getByRole("heading", { name: "Werewolf rules card" })).toBeVisible();
  await p.screenshot(shots("stock-npc-builder"));

  // The rating holds the count; a discipline off the werewolf's list is refused.
  await add("power:Dominate");
  await expect(p.getByText("Werewolf Stock NPCs cannot specialise in Dominate.")).toBeVisible();
  await expect(p.getByRole("listitem", { name: "Dominate" })).toHaveCount(0);
  // Any kind may take the SRD's Infernal Investment, which opens Dark Thaumaturgy (#414).
  await add("power:Infernal Investment");
  await expect(p.getByRole("heading", { name: "Specialisations (3 of 3)" })).toBeVisible();
  await expect(block.getByText(/^Infernal Investment/)).toContainText("Every Dark Thaumaturgy ritual");
  await add("skill:Melee");
  await expect(p.getByText("as many specialisations as its rating")).toBeVisible();
  await expect(p.getByRole("listitem", { name: "Melee" })).toHaveCount(0);
});

test("a storyteller makes a Stock werewolf a full sheet, which plays with Rage and no Beast", async ({ browser }) => {
  const custodian = await person(browser, "tosheet-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tosheet-lead");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Burrs ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;

  const p = lead.page;
  const stock = await p.request.post(`/api/troupes/${troupeId}/npcs`, {
    headers,
    data: {
      name: "Grinds-the-Bone",
      npc_kind: "werewolf",
      npc_form: "stock",
      stock: { rating: 3, specializations: [{ type: "skill", name: "Brawl" }, { type: "power", name: "Celerity" }], notes: "Hunts alone." },
    },
  });
  expect(stock.status(), await stock.text()).toBe(201);
  const npc = (await stock.json()).id as string;

  await p.goto(`/troupes/${troupeId}/npcs/${npc}`);
  await p.getByRole("button", { name: "Make this a full sheet…" }).click();
  const confirm = p.getByRole("dialog", { name: "Make Grinds-the-Bone a full sheet?" });
  await expect(confirm.getByText("Physical, Social and Mental are each its test pool, rating × 2: 6.")).toBeVisible();
  await expect(p.getByText("It cannot be turned back.")).toBeVisible();
  await confirm.getByRole("button", { name: "Make a full sheet" }).click();

  // Its sheet starts from the Stock data, labelled as a werewolf, with the rules card at hand.
  await expect(p).toHaveURL(new RegExp(`/characters/${npc}$`));
  await expect(p.getByRole("heading", { name: "Grinds-the-Bone" })).toBeVisible();
  await expect(p.getByText("Werewolf", { exact: true }).first()).toBeVisible();
  await p.getByRole("button", { name: "Rules card" }).click();
  await expect(p.getByRole("dialog", { name: "Rules card" }).getByRole("heading", { name: "Werewolf rules card" })).toBeVisible();
  await p.keyboard.press("Escape");
  await p.locator("main").getByRole("link", { name: "Sheet", exact: true }).click();
  await expect(p.getByText("Brawl", { exact: true }).first()).toBeVisible();
  const sheet = await (await p.request.get(`/api/characters/${npc}/sheet`)).json();
  const rating = (name: string) => sheet.traits.find((t: { name: string }) => t.name === name)?.rating;
  expect([rating("Brawl"), rating("Celerity"), rating("Physical")]).toEqual([3, 3, 6]);

  // Its Play View has Rage in Blood's place, and no Beast, Humanity or Generation.
  await p.goto(`/play/characters/${npc}?tab=tracker`);
  await expect(p.getByText("Werewolf", { exact: true }).first()).toBeVisible();
  await expect(p.getByLabel("Rage: 10 of 10")).toBeVisible();
  await expect(p.getByLabel(/^Beast traits/)).toHaveCount(0);
  await expect(p.getByLabel(/^Humanity/)).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Frenzy" })).toHaveCount(0);
  await expect(p.getByText(/Generation \d/)).toHaveCount(0);
  await p.getByRole("button", { name: "Spend Rage" }).first().click();
  await expect(p.getByLabel("Rage: 9 of 10")).toBeVisible();
  await p.screenshot(shots("npc-werewolf-play"));
});

test("a sheeted Mortal NPC's Play View has no Beast or Humanity panel", async ({ browser }) => {
  const custodian = await person(browser, "mortal-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "mortal-lead");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Thistles ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;

  const p = lead.page;
  const npc = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Constable Marsh", npc_kind: "mortal", wizard: false } });
  expect(npc.status(), await npc.text()).toBe(201);
  const id = (await npc.json()).id as string;

  await p.goto(`/characters/${id}`);
  await expect(p.getByText("Mortal", { exact: true }).first()).toBeVisible();
  // The quick build leaves out what a mortal does not have.
  await expect(p.getByRole("heading", { name: "Skills" })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Humanity" })).toHaveCount(0);

  await p.goto(`/play/characters/${id}?tab=tracker`);
  await expect(p.getByLabel("Blood: 5 of 5")).toBeVisible();
  await expect(p.getByLabel("Willpower: 6 of 6")).toBeVisible();
  await expect(p.getByLabel(/^Beast traits/)).toHaveCount(0);
  await expect(p.getByLabel(/^Humanity/)).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Frenzy" })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Feed" })).toHaveCount(0);
});

test("storytellers give an NPC powers, and one out of order is marked until it is in order", async ({ browser }) => {
  const custodian = await person(browser, "powers-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "powers-lead");
  const troupeName = `Court of Kindling ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  const created = custodian.page.waitForResponse((r) => r.url().endsWith("/api/troupes") && r.request().method() === "POST");
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  const troupeId = (await (await created).json()).id as string;
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  const p = lead.page;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Matriarch Odile", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  for (const [category, name, rating] of [
    ["clan", "Toreador", null],
    ["backgrounds", "Generation", 2],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category, name, rating, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
  }

  // Each tap saves and works the marks out again, which takes a while under load.
  const slowly = expect.configure({ timeout: 20_000 });
  await p.goto(`/characters/${npc}`);
  await slowly(p.getByRole("heading", { name: "Techniques", exact: true })).toBeVisible();

  // A technique is found by search and added at once; its disciplines are missing, so it is marked.
  await p.getByLabel("Search Techniques").fill("Da Shealladh");
  await p.getByRole("checkbox", { name: "An Da Shealladh" }).click();
  await slowly(p.getByRole("checkbox", { name: "An Da Shealladh" })).toBeChecked();
  await p.getByLabel("Search Techniques").fill("");
  await slowly(p.getByRole("checkbox", { name: "An Da Shealladh" })).toBeChecked();
  await slowly(p.getByText("Marked: An Da Shealladh needs Dementation 3 and Auspex 2.")).toBeVisible();

  // Adding the disciplines clears the mark.
  await p.getByLabel("Search Disciplines").fill("Dementation");
  await p.getByRole("button", { name: "Dementation 3", exact: true }).click();
  await slowly(p.getByRole("button", { name: "Dementation 3", exact: true })).toHaveAttribute("aria-pressed", "true");
  await p.getByLabel("Search Disciplines").fill("Auspex");
  await p.getByRole("button", { name: "Auspex 2", exact: true }).click();
  await slowly(p.getByRole("button", { name: "Auspex 2", exact: true })).toHaveAttribute("aria-pressed", "true");
  await slowly(p.getByText("Marked: An Da Shealladh")).toHaveCount(0);
  await slowly(p.getByRole("checkbox", { name: "An Da Shealladh" })).toBeChecked();

  // An elder power, a ritual (shown with its level) and an extra in-clan discipline.
  await p.getByLabel("Search Elder & luminary powers").fill("Crimson Fury");
  await p.getByRole("checkbox", { name: "Animalism: Crimson Fury" }).click();
  await slowly(p.getByRole("checkbox", { name: "Animalism: Crimson Fury" })).toBeChecked();
  await slowly(p.getByText("Marked: A Neonate's or Ancilla's blood is too thin for elder powers.")).toBeVisible();

  await p.getByLabel("Search Rituals").fill("Abyssal Ichor");
  await p.getByRole("checkbox", { name: "Abyssal: Abyssal Ichor" }).click();
  await slowly(p.getByRole("checkbox", { name: "Abyssal: Abyssal Ichor" })).toBeChecked();

  await p.getByLabel("Search Extra in-clan disciplines").fill("Fortitude");
  await p.getByRole("checkbox", { name: "Fortitude", exact: true }).click();
  await slowly(p.getByRole("checkbox", { name: "Fortitude", exact: true })).toBeChecked();

  // They are on the sheet, and stay after a reload; one tap takes a power off.
  await p.reload();
  for (const name of ["An Da Shealladh", "Animalism: Crimson Fury", "Abyssal: Abyssal Ichor", "Fortitude"]) {
    await slowly(p.getByRole("checkbox", { name, exact: true })).toBeChecked();
  }
  await p.getByRole("checkbox", { name: "An Da Shealladh" }).click();
  await slowly(p.getByRole("checkbox", { name: "An Da Shealladh" })).toHaveCount(0);
});
