import { expect, test } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian } from "./support";

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
  await p.getByRole("button", { name: "Give Prince Vasquez a title" }).click();
  await p.getByRole("dialog").getByLabel("Title").fill("Prince");
  await p.screenshot(shots("give-title"));
  await p.getByRole("dialog").getByLabel("Title").press("Enter");
  await expect(p.getByRole("button", { name: "Take the title Prince from Prince Vasquez" })).toBeVisible();
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
  await p.screenshot(shots("npcs"));
  await p.getByRole("link", { name: "Play Sheriff Ilse" }).click();
  await expect(p.getByRole("heading", { name: "Sheriff Ilse" })).toBeVisible();
  await expect(p.getByRole("tab", { name: "Tracker" })).toBeVisible();
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
  const wolf = p.getByRole("listitem", { name: "Bites-the-Hand" });
  await expect(wolf.getByText("Werewolf")).toBeVisible();
  await expect(wolf.getByText("Stock", { exact: true })).toBeVisible();
  await expect(wolf.getByText("Rating 3")).toBeVisible();
  // A Stock NPC plays from a Play View of its own.
  await expect(p.getByRole("link", { name: "Play Bites-the-Hand" })).toBeVisible();

  // A sheeted mage goes to its quick build, on the Vampire sheet.
  await p.getByLabel("Name").fill("Sarah Juniper");
  await p.getByLabel("Kind", { exact: true }).selectOption("mage");
  await p.getByRole("radio", { name: "Sheeted" }).click();
  await p.getByRole("button", { name: "Quick build" }).click();
  await expect(p.getByRole("heading", { name: "Sarah Juniper" })).toBeVisible();

  await p.goto(`/troupes/${troupeId}/npcs`);
  const mage = p.getByRole("listitem", { name: "Sarah Juniper" });
  await expect(mage.getByText("Mage")).toBeVisible();
  await expect(mage.getByText("Sheeted")).toBeVisible();
  await expect(p.getByRole("link", { name: "Play Sarah Juniper" })).toBeVisible();
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
  await p.getByRole("listitem", { name: "Gnashes-the-Moon" }).getByRole("link", { name: "Gnashes-the-Moon", exact: true }).click();
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
