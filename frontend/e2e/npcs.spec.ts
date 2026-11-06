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
  await p.locator("main").getByRole("link", { name: "NPCs", exact: true }).click();
  await expect(p.getByRole("heading", { name: "New NPC" })).toBeVisible();
  await p.getByLabel("Name").fill("Prince Vasquez");
  await p.getByRole("button", { name: "Quick build" }).click();
  await expect(p.getByRole("heading", { name: "Prince Vasquez" })).toBeVisible();

  await p.getByLabel("Clan", { exact: true }).selectOption("Ventrue");
  await expect(p.getByLabel("Clan", { exact: true })).toHaveValue("Ventrue");
  // A Prince must be Camarilla: a title of a sect goes only to its characters.
  await p.getByLabel("Sect", { exact: true }).selectOption("Camarilla");
  await expect(p.getByLabel("Sect", { exact: true })).toHaveValue("Camarilla");
  await p.getByRole("button", { name: "Social 7", exact: true }).click(); // attributes: 3 a dot
  await expect(p.getByText("21 XP")).toBeVisible();
  // Each attribute's focus is chosen beside it, one of three; choosing again swaps it.
  await expect(p.getByRole("heading", { name: "Focuses" })).toHaveCount(0);
  await p.getByLabel("Social focus").selectOption("Charisma");
  await expect(p.getByLabel("Social focus")).toHaveValue("Charisma");
  await p.getByLabel("Social focus").selectOption("Manipulation");
  await expect(p.getByLabel("Social focus")).toHaveValue("Manipulation");
  await expect(p.getByText("21 XP")).toBeVisible(); // focuses are free
  await p.getByRole("button", { name: "Leadership 3", exact: true }).click(); // 1 + 2 + 3
  await expect(p.getByText("27 XP")).toBeVisible();
  // Morality is one path at one rating: moving to a Path keeps the rating, free.
  await expect(p.getByLabel("Morality", { exact: true })).toHaveValue("Humanity");
  await p.getByRole("button", { name: "Humanity 4", exact: true }).click();
  await expect(p.getByRole("button", { name: "Humanity 4", exact: true })).toHaveAttribute("aria-pressed", "true");
  await p.getByLabel("Morality", { exact: true }).selectOption("Caine");
  await expect(p.getByRole("button", { name: "Caine 4", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(p.getByRole("button", { name: /^Humanity \d+$/ })).toHaveCount(0);
  await expect(p.getByText("27 XP")).toBeVisible();
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

  // Titles are given on the troupe's Characters tab.
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await p.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
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

  // The NPC list: badges for those ticked or for every NPC, and each one's Play View.
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const another = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers: { "X-Horatio": "1" }, data: { name: "Sheriff Ilse", wizard: false } });
  expect(another.status(), await another.text()).toBe(201);
  await p.goto(`/troupes/${troupeId}/npcs`);
  await p.getByLabel("Select Prince Vasquez").check();
  let badgesTab = p.context().waitForEvent("page");
  await p.getByRole("button", { name: "Badges for selected (1)" }).click();
  let badges = await badgesTab;
  await expect(badges.getByRole("article")).toHaveCount(1);
  await expect(badges.getByRole("article", { name: "Badge for Prince Vasquez" }).getByText("Prince", { exact: true })).toBeVisible();
  await badges.close();
  badgesTab = p.context().waitForEvent("page");
  await p.getByRole("button", { name: "Badges for all NPCs" }).click();
  badges = await badgesTab;
  await expect(badges.getByRole("article")).toHaveCount(2);
  await expect(badges.getByRole("article", { name: "Badge for Sheriff Ilse" })).toBeVisible();
  await badges.close();
  // Each NPC's actions are behind its ⋯: listing it on the Who's Who, its badge, and Play.
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
    ["attributes", "Physical", 5],
    ["skills", "Brawl", 3],
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
  await p.goto(`/troupes/${troupeId}/npcs`);
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
  await p.getByRole("button", { name: "Actions for Bites-the-Hand" }).click();
  await expect(p.getByRole("menuitem", { name: "Play", exact: true })).toBeVisible();
  await p.keyboard.press("Escape");

  // A sheeted mage goes to its quick build, on the Vampire sheet.
  await p.getByLabel("Name").fill("Sarah Juniper");
  await p.getByLabel("Kind", { exact: true }).selectOption("mage");
  await p.getByRole("radio", { name: "Sheeted" }).click();
  await p.getByRole("button", { name: "Quick build" }).click();
  await expect(p.getByRole("heading", { name: "Sarah Juniper" })).toBeVisible();

  await p.goto(`/troupes/${troupeId}/npcs`);
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
  await p.goto(`/troupes/${troupeId}/npcs`);
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
