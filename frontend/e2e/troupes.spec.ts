import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, backstoryOptional, characterTab, builtVampire, ATTRIBUTES_AND_FOCUSES, PASSWORD } from "./support";

/** A troupe's setup: its rules, XP range, staff, profile and archiving, and asking for one. */

closeContextsAfterEach();

test("a troupe changes what new characters start with and their downtime actions", async ({ browser }) => {
  const custodian = await person(browser, "start-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "start-lead");
  const player = await person(browser, "start-player");
  const troupeName = `Court of Embers ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // The lead gives new characters a bigger merit budget.
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await l.getByRole("link", { name: "Customise", exact: true }).click();
  await l.getByRole("link", { name: "Rules", exact: true }).click();
  await l.getByRole("link", { name: "Starting points", exact: true }).click();
  await l.getByRole("button", { name: "Change starting Merits" }).click();
  await l.getByLabel("Points for merits").fill("9");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("The rule set's: 7 points")).toBeVisible();
  await l.screenshot(shots("starting"));
  // …and four downtime actions a cycle instead of three.
  await l.getByRole("link", { name: "Downtime actions", exact: true }).click();
  await l.getByRole("button", { name: "Change actions for Everyone" }).click();
  await l.getByLabel("Downtime actions each cycle").fill("4");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("Replaced here")).toBeVisible();
  await expect(l.getByText("4 downtime actions")).toBeVisible();
  await l.screenshot(shots("actions"));

  // A character built for the troupe has that budget in the wizard.
  const p = player.page;
  await p.reload();
  await p.getByLabel("Name").fill("Mara");
  await p.getByLabel("Which troupe will you play in?").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Create" }).click();
  await p.getByLabel("Clan").selectOption("Brujah");
  await expect(p.getByLabel("Clan")).toHaveValue("Brujah");
  for (const heading of ["Attributes", "Focuses", "Skills", "Backgrounds", "Disciplines", "Merits & flaws"]) {
    // A vampire needs Generation before leaving Backgrounds.
    if (heading === "Disciplines") await p.getByRole("button", { name: "Generation 1", exact: true }).click();
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
  }
  await expect(p.getByText("0 of 9 points")).toBeVisible();
});

test("Customise opens on Overview, a setup checklist and the house settings, and Checks come in folded groups that a search looks through (#377)", async ({ browser }) => {
  const custodian = await person(browser, "tally-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tally-lead");
  const troupeName = `House of Tallies ${run}`;
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // Customise opens on Overview: nothing is set up yet, and every rule plays as the book has it.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}`);
  await l.getByRole("link", { name: "Customise", exact: true }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/customise$`));
  const steps = l.getByRole("list", { name: "Setting up" });
  await expect(steps.getByRole("listitem")).toHaveCount(4);
  await expect(l.getByText("0 of 4 done")).toBeVisible();
  const glance = l.locator("section").filter({ has: l.getByRole("heading", { name: "House settings at a glance" }) });
  await expect(glance.getByText(/^0 of \d+ played differently$/)).toBeVisible();
  await expect(glance.getByText(/Discord: not set up on this server/)).toBeVisible();
  await l.screenshot(shots("customise-overview"));

  // Checks open on the troupe's house rules, of which there are none yet.
  await steps.getByRole("link", { name: /^House rules\W+to do/ }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/rules$`));
  await expect(l.getByText("No house rules yet.")).toBeVisible();
  // All of them come in groups, folded, each with its count.
  await l.getByRole("button", { name: /^All checks/ }).click();
  const clanMerits = l.locator("details").filter({ hasText: "Clan merits, only for their clan or bloodline" });
  await expect(clanMerits).toContainText(/\d{3} checks/);
  await expect(clanMerits).toHaveJSProperty("open", false);
  await expect(l.getByLabel(/^Setting for:/)).toHaveCount(0);
  const techniques = l.locator("details").filter({ has: l.getByRole("heading", { name: "Techniques", exact: true }) });
  await techniques.getByRole("heading", { name: "Techniques", exact: true }).click();
  await expect(techniques.getByLabel(/^Setting for: Animal Swarm needs/)).toBeVisible();

  // A search looks through them all, and opens the group it finds the check in.
  await l.getByLabel("Search checks").fill("Calm Heart");
  await expect(l.getByRole("group", { name: "Checks by kind" }).locator("details")).toHaveCount(1);
  await expect(l.locator("details").filter({ has: l.getByRole("heading", { name: "Merits", exact: true }) })).toContainText("1 of 29 checks");
  await l.getByLabel(/Setting for: Brujah cannot take Calm Heart/).selectOption({ label: "Off" });
  await expect(l.getByText("Saved: Calm Heart is now Off")).toBeVisible();
  await expect(l.getByRole("button", { name: "House rules (1)" })).toBeVisible();
  await l.screenshot(shots("customise-checks"));

  // Overview counts it.
  await l.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(steps.getByRole("link", { name: /^House rules\W+done/ })).toBeVisible();
  await expect(glance.getByText(/^1 of \d+ played differently$/)).toBeVisible();
});

test("the lead builds a check of the troupe's own from blocks, and it refuses a purchase (#432)", async ({ browser }) => {
  const custodian = await person(browser, "ownchk-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "ownchk-lead");
  const player = await person(browser, "ownchk-player");
  const troupeName = `House of Own Checks ${run}`;
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // The lead keeps Iron Will for the Ventrue: a trait from the catalogue, and a clan block.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/rules`);
  await l.getByRole("button", { name: "Add a check" }).click();
  const form = l.getByRole("region", { name: "A new check" });
  await form.getByLabel("Kind of trait", { exact: true }).selectOption({ label: "Merits" });
  await form.getByLabel("Trait", { exact: true }).selectOption("Iron Will");
  await form.getByLabel("It", { exact: true }).selectOption({ label: "Is allowed only when…" });
  await form.getByLabel("Condition: add a block").selectOption({ label: "Clan or its bloodlines…" });
  await form.getByLabel("Condition 1: add a trait").selectOption("Ventrue");
  const preview = form.getByRole("region", { name: "Preview" });
  await expect(preview).toContainText("Iron Will: refused unless the clan is Ventrue or one of its bloodlines.");
  await expect(preview).toContainText("None of the troupe's characters breaks it now.");
  await form.getByLabel("Message the player sees").fill("Iron Will is for the Ventrue here.");
  await form.getByRole("button", { name: "Add the check" }).click();
  const own = l.getByRole("list", { name: "The troupe's own checks" });
  await expect(own.getByRole("listitem").filter({ hasText: "Iron Will is for the Ventrue here." })).toContainText("Our own");
  await l.screenshot(shots("customise-own-check"));

  // A Brujah being built for the troupe cannot take it on the Merits step.
  const p = player.page;
  const character = await p.request.post("/api/characters", { headers, data: { splat: "vampire", name: "Osric Vane", building_troupe_id: troupeId } });
  expect(character.status(), await character.text()).toBe(201);
  const characterId: string = (await character.json()).id;
  const clan = await p.request.put(`/api/characters/${characterId}/traits`, { headers, data: { category: "clan", name: "Brujah", rating: null } });
  expect(clan.status(), await clan.text()).toBe(200);
  const bought = await p.request.put(`/api/characters/${characterId}/creation/categories/merits`, { headers, data: { picks: [{ name: "Iron Will" }] } });
  expect(bought.status()).toBe(409);
  expect((await bought.json()).detail).toContain("Iron Will is for the Ventrue here.");

  // The players' House rules tab lists it as the troupe's own.
  await p.goto(`/troupes/${troupeId}/house-rules`);
  await expect(p.getByText("Iron Will is for the Ventrue here.")).toBeVisible();
});

test("a troupe's players read its house rules: a price the lead changes shows there beside the book's", async ({ browser }) => {
  const custodian = await person(browser, "lantern-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "lantern-lead");
  const player = await person(browser, "lantern-player");
  const troupeName = `House of Lanterns ${run}`;
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // The lead prices attributes at 4 XP a dot, with a note for players.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/rules/costs`);
  await l.getByRole("button", { name: "Change the price for All Attributes" }).click();
  await l.getByLabel("How it's priced").selectOption({ label: "The same for each dot" });
  await l.getByLabel("XP per dot").fill("4");
  await l.getByLabel("Note for players").fill("Training is slow here");
  await l.getByRole("button", { name: "Save price" }).click();
  await expect(l.getByText("Only house rules (1)")).toBeVisible();

  // A player's character visits the troupe; from its Troupes tab the player opens the house rules.
  const p = player.page;
  const id = await builtVampire(p, "Liesl", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const joined = await p.request.post(`/api/characters/${id}/troupes`, { headers: { "X-Horatio": "1" }, data: { troupe_id: troupeId } });
  expect(joined.status(), await joined.text()).toBeLessThan(300);
  await p.goto(`/characters/${id}`);
  await characterTab(p, "Troupes");
  await p.getByRole("link", { name: `${troupeName}'s house rules` }).click();
  await expect(p).toHaveURL(new RegExp(`/troupes/${troupeId}/house-rules$`));
  const costs = p.locator("section").filter({ has: p.getByRole("heading", { name: "Costs", exact: true }) });
  const attributes = costs.getByRole("listitem").filter({ hasText: "All Attributes" });
  await expect(attributes.getByText("4 XP per dot")).toBeVisible();
  await expect(attributes.getByText("By the book: 3 XP per dot")).toBeVisible();
  await expect(attributes.getByText("House rule: Training is slow here")).toBeVisible();
  await expect(p.getByText(/The storytellers approve it before the troupe accepts the character/)).toBeVisible();
  await p.screenshot(shots("house-rules"));
});

test("a player looks up the rules: a power by name and by its summary, then as played in a troupe, a house price shown and a banned merit hidden (#422)", async ({ browser }) => {
  const custodian = await person(browser, "rulebook-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "rulebook-lead");
  const player = await person(browser, "rulebook-player");
  const troupeName = `Hall of Statutes ${run}`;
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  // The troupe sells Absent Sway for 2 points rather than 3, and bans Calm Heart.
  for (const data of [
    { category: "merits", trait: "Absent Sway", scheme: "fixed", rate: 2 },
    { category: "merits", trait: "Calm Heart", scheme: "not_allowed", text: "No one keeps calm here" },
  ]) {
    const priced = await lead.page.request.post(`/api/troupes/${troupeId}/costs`, { headers: { "X-Horatio": "1" }, data });
    expect(priced.status(), await priced.text()).toBe(201);
  }

  // From the main nav, the book's rules: a power found by its name, and by a word of its summary.
  const p = player.page;
  await p.getByRole("link", { name: "Rules reference" }).click();
  const search = p.getByRole("searchbox", { name: "Search the rules" });
  const entry = (name: string) => p.getByTestId("rules-entry").filter({ has: p.getByRole("heading", { name, exact: true }) });
  await search.fill("majesty");
  await expect(entry("Majesty")).toContainText("Presence 5");
  await search.fill("act against you");
  await expect(entry("Majesty")).toBeVisible();
  // A Dark Thaumaturgy ritual, from the V20 LARP SRD, links its page there (#414).
  await search.fill("vile swarm");
  const swarm = entry("Dark Thaumaturgy: Vile Swarm");
  await expect(swarm).toContainText("Level 4");
  await expect(swarm.getByRole("link", { name: "V20 LARP SRD" })).toHaveAttribute("href", "https://www.oneworldofdarkness.com/srd-v20/rituals/vile-swarm");

  // The merits a clan needs, and Calm Heart as the book has it.
  await search.fill("");
  await p.getByRole("button", { name: /^Merits/ }).click();
  await p.getByLabel("Clan").selectOption("Toreador");
  await expect(entry("Absent Sway")).toContainText("3 points");
  await p.getByLabel("Clan").selectOption("");
  await search.fill("calm heart");
  await expect(entry("Calm Heart")).toBeVisible();

  // As played in the troupe: Calm Heart is gone, unless asked for, marked as not allowed.
  await p.getByLabel("As played in").selectOption({ label: troupeName });
  await expect(p.getByText(`Nothing matches “calm heart”.`)).toBeVisible();
  await p.getByLabel(`Show the 1 not allowed in ${troupeName}`).check();
  await expect(entry("Calm Heart")).toContainText(`Not allowed in ${troupeName}`);
  await expect(entry("Calm Heart")).toContainText("House rule: No one keeps calm here");

  // Absent Sway at the troupe's price, beside the book's.
  await search.fill("absent sway");
  const sway = entry("Absent Sway");
  await expect(sway).toContainText("2 points");
  await expect(sway.getByText("House rule", { exact: true })).toBeVisible();
  await expect(sway).toContainText("By the book: 3 points");
  await p.screenshot(shots("rules-browser"));

  // The troupe's House rules page leads back here, the troupe chosen.
  await p.getByRole("link", { name: "What it changes" }).click();
  await expect(p).toHaveURL(new RegExp(`/troupes/${troupeId}/house-rules$`));
  await p.getByRole("link", { name: "Browse every rule as played here" }).click();
  await expect(p.getByLabel("As played in")).toHaveValue(troupeId);
});

test("a troupe's XP floor and ceiling: new characters start at the floor, and staff settle a joiner's XP", async ({ browser }) => {
  // A whole character creation, then a home troupe request.
  test.slow();
  const custodian = await person(browser, "floor-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "floor-lead");
  const player = await person(browser, "floor-player");
  const troupeName = `Court of Bones ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  await backstoryOptional(custodian.page, troupeName);

  // The chronicle began before Horatio: the lead sets the floor and ceiling by hand, in Customise.
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await l.getByRole("link", { name: "Customise", exact: true }).click();
  await l.getByRole("link", { name: "Troupe settings", exact: true }).click();
  await l.getByRole("button", { name: "Set by hand" }).click();
  await l.getByLabel("Floor", { exact: true }).fill("100");
  await l.getByLabel("Ceiling", { exact: true }).fill("120");
  await l.getByLabel("Why", { exact: true }).fill("Chronicle began in 2019");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("(30 starting + 70 set by hand)")).toBeVisible();
  await expect(l.getByText("(30 starting + 90 set by hand)")).toBeVisible();
  await l.screenshot(shots("xp-range"));

  // Players see where the troupe stands on its page.
  const p = player.page;
  await p.reload();
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: "XP floor and ceiling" })).toBeVisible();
  await expect(p.getByText("100 XP", { exact: true })).toBeVisible();

  // A character built for the troupe starts at its floor.
  await p.getByRole("link", { name: "Characters" }).click();
  await p.getByLabel("Name").fill("Mara");
  await p.getByLabel("Which troupe will you play in?").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Create" }).click();
  await p.getByLabel("Clan").selectOption("Brujah");
  await expect(p.getByLabel("Clan")).toHaveValue("Brujah");
  await p.getByLabel("Sect").selectOption("Camarilla");
  const next = async (heading: string) => {
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
  };
  const tap = async (...dots: string[]) => {
    for (const dot of dots) await p.getByRole("button", { name: dot, exact: true }).click();
  };
  await next("Attributes");
  await tap("Physical 7", "Social 5", "Mental 3");
  await next("Focuses");
  await tap("Strength 1", "Wits 1", "Charisma 1");
  await next("Skills");
  await tap("Brawl 4", "Dodge 3", "Athletics 3", "Awareness 2", "Empathy 2", "Firearms 2");
  await tap("Investigation 1", "Leadership 1", "Medicine 1", "Melee 1");
  await next("Backgrounds");
  await tap("Fame 3", "Herd 2", "Generation 1");
  await next("Disciplines");
  await tap("Celerity 2", "Potence 1", "Presence 1");
  await next("Merits & flaws");
  await next("Review");
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  await characterTab(p, "Experience");
  await expect(p.getByText(`Starting experience: ${troupeName}'s XP floor`)).toBeVisible();

  // Mara was played elsewhere first: her player adds that XP themselves.
  await p.getByLabel("XP", { exact: true }).fill("30");
  await p.getByLabel("Why", { exact: true }).fill("Played at another troupe");
  await p.getByRole("button", { name: "Add", exact: true }).click();
  await expect(p.getByText("self-entered", { exact: true })).toBeVisible();

  // Asking to make the troupe her home, she sees she is above its ceiling.
  await characterTab(p, "Troupes");
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: troupeName });
  await expect(p.getByText("That is 10 XP above the ceiling.", { exact: false })).toBeVisible();
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(/Waiting for .* storytellers/)).toBeVisible();

  // The lead sees the self-entered XP apart, and what is above the ceiling, and removes it.
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: /Approvals/ }).click();
  await expect(l.getByLabel("Self-entered XP: 30")).toBeVisible();
  await l.getByLabel("Above the ceiling by 10 XP").selectOption({ label: "Remove the 10 XP above the ceiling" });
  await expect(l.getByText("After joining it will have been given 120 XP.", { exact: false })).toBeVisible();
  await l.screenshot(shots("xp-approval"));
  await l.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();

  // Taking it away is its own entry in Mara's XP history.
  await characterTab(p, "Experience");
  await expect(p.getByText(`XP above ${troupeName}'s ceiling of 120`)).toBeVisible();
  await expect(p.getByText("above a ceiling", { exact: true })).toBeVisible();
});

test("storytellers filter the troupe's characters and print what they find", async ({ browser }) => {
  const custodian = await person(browser, "filter-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "filter-lead");
  const troupeName = `Court of Mirrors ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Three NPCs, made straight through the API (the builder has its own test).
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  for (const [name, clan, occult] of [
    ["Prince", "Ventrue", 4],
    ["Mara", "Tremere", 1],
    ["Nell", "Giovanni", 0],
  ] as const) {
    const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(made.status(), await made.text()).toBe(201);
    const id = (await made.json()).id;
    const rate = (category: string, trait: string, rating: number | null) =>
      p.request.put(`/api/characters/${id}/npc/ratings`, { headers, data: { category, name: trait, rating, detail: "" } });
    expect((await rate("clan", clan, null)).status()).toBe(200);
    if (occult) expect((await rate("skills", "Occult", occult)).status()).toBe(200);
  }

  await p.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await expect(p.getByText("3 of 3 characters")).toBeVisible();
  await expect(p.getByRole("button", { name: "Remove “Is active”" })).toBeVisible(); // retired characters are hidden by default

  // Occult below 3, and (Tremere, or the Giovanni family).
  await p.getByRole("button", { name: "Filter" }).click();
  await p.getByRole("button", { name: "+ Condition", exact: true }).click();
  const occult = p.getByRole("group", { name: "Condition" }).nth(1);
  await occult.getByLabel("Category").selectOption({ label: "Skills" });
  await occult.getByLabel("Trait").selectOption("Occult");
  await occult.getByLabel("How").selectOption({ label: "below" });
  await occult.getByLabel("Number").fill("3");
  await expect(p.getByText("2 of 3 characters")).toBeVisible();
  await p.getByRole("button", { name: "+ Group" }).click();
  await p.getByLabel("Group match").selectOption({ label: "any of these (or)" });
  const tremere = p.getByRole("group", { name: "Condition" }).nth(2);
  await tremere.getByLabel("Value").selectOption("Tremere");
  await p.getByRole("button", { name: "Add a condition to this group" }).click();
  const giovanni = p.getByRole("group", { name: "Condition" }).nth(3);
  await giovanni.getByLabel("What").selectOption({ label: "Clan, sect, focus…" });
  await giovanni.getByLabel("How").selectOption({ label: "is in the family of" });
  await giovanni.getByLabel("Value").selectOption("Giovanni");
  await expect(p.getByText("2 of 3 characters")).toBeVisible();
  await expect(p.getByText("(Clan is Tremere, or Clan is in the Giovanni family)")).toBeVisible();
  const list = p.locator("main ul.divide-y");
  await expect(list.getByRole("link", { name: "Prince" })).toHaveCount(0);
  await expect(list.getByText("Occult 1")).toBeVisible(); // the number the filter compares
  await expect(list.getByText("Occult 0")).toBeVisible();
  await p.screenshot(shots("filter"));

  // The filter is in the URL, so it survives a reload.
  await p.reload();
  await expect(p.getByText("2 of 3 characters")).toBeVisible();

  // Print all prints what the filter shows.
  await p.getByRole("button", { name: "Print…" }).click();
  const printTab = p.context().waitForEvent("page");
  await p.getByRole("button", { name: "Print all 2" }).click();
  const printed = await printTab;
  await expect(printed.getByText("2 sheets", { exact: true })).toBeVisible();
  await printed.close();
});

test("the troupe list says what each troupe is, whether it takes new players and where you play, and keeps the ask form shut", async ({ browser }) => {
  const custodian = await person(browser, "chooser-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "chooser-lead");
  const player = await person(browser, "chooser-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT" | "PATCH", url: string, data: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const troupeName = `Court of the Corn Exchange ${run}`;
  const troupeId = (await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle })).id;
  await backstoryOptional(custodian.page, troupeId);
  await send(lead.page, "PATCH", `/api/troupes/${troupeId}`, {
    description: "A **Camarilla** court that meets under the old dome.\n\nGames run monthly; see the profile for more.",
  });
  await send(lead.page, "PUT", `/api/troupes/${troupeId}/profile`, { new_players: "welcoming", venue: { region: "Leeds" } });
  const id = await builtVampire(player.page, "Clémence Aubry", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const asked = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});

  // The player's own troupe comes first, with the start of its description as plain text.
  const p = player.page;
  await p.goto("/troupes");
  const list = p.locator("main ul").first();
  await expect(list.getByRole("listitem").first()).toContainText(troupeName);
  const row = list.getByRole("listitem").filter({ hasText: troupeName });
  await expect(row.getByText("A Camarilla court that meets under the old dome.", { exact: true })).toBeVisible();
  await expect(row.getByText("Leeds", { exact: true })).toBeVisible();
  await expect(row.getByText("Welcoming new players", { exact: true })).toBeVisible();
  await expect(row.getByText("You play here", { exact: true })).toBeVisible();
  await expect(row.getByText("Clémence Aubry", { exact: true })).toBeVisible();

  // Asking for a troupe of your own is one line until opened.
  const open = p.getByRole("button", { name: "Ask for a new troupe" });
  await expect(open).toHaveAttribute("aria-expanded", "false");
  await expect(p.getByLabel("Troupe name")).toHaveCount(0);
  await p.screenshot(shots("troupes-list"));

  // Its staff see that they run it.
  await lead.page.goto("/troupes");
  const theirs = lead.page.locator("main ul").first().getByRole("listitem").filter({ hasText: troupeName });
  await expect(theirs.getByText("You run this", { exact: true })).toBeVisible();
  await expect(theirs.getByText("You play here", { exact: true })).toHaveCount(0);
});

test("someone asks for a troupe of their own, and the custodian approves it", async ({ browser }) => {
  const custodian = await person(browser, "requests-custodian");
  makeCustodian(custodian.email);
  const asker = await person(browser, "requests-asker");
  const troupeName = `Court of Cinders ${run}`;

  const a = asker.page;
  await a.getByRole("link", { name: "Troupes" }).click();
  await a.getByRole("button", { name: "Ask for a new troupe" }).click();
  await a.getByLabel("Troupe name").fill(troupeName);
  await a.getByLabel("Note to the custodian").fill("Eight players ready.");
  await a.getByRole("button", { name: "Send request" }).click();
  const mine = a.getByRole("listitem").filter({ hasText: troupeName });
  await expect(mine.getByText("Waiting", { exact: true })).toBeVisible();

  // It waits on the custodian's bell and under Custodian → Troupe requests.
  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: /Troupe requests/ }).click();
  const request = c.getByRole("listitem").filter({ hasText: troupeName });
  await expect(request.getByText("Eight players ready.")).toBeVisible();
  await c.screenshot(shots("troupe-request"));
  await request.getByRole("button", { name: "Approve and make the troupe" }).click();
  await expect(c.getByRole("link", { name: troupeName })).toBeVisible();

  // What is running, and that the database is on its latest migration.
  await c.getByRole("link", { name: "System", exact: true }).click();
  await expect(c.getByText("Up to date", { exact: true })).toBeVisible();
  await c.screenshot(shots("custodian-system"));

  // The asker now leads it.
  await a.reload();
  await expect(mine.getByText("Approved", { exact: true })).toBeVisible();
  await a.locator("main").getByRole("link", { name: troupeName }).first().click();
  await expect(a.getByText("Lead storyteller").first()).toBeVisible();
});

test("archiving a troupe lets its characters go and ends its cycle, and the custodian reopens it", async ({ browser }) => {
  const custodian = await person(browser, "closing-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "closing-lead");
  const player = await person(browser, "closing-player");
  const visitor = await person(browser, "closing-visit");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const troupeName = `Court of Last Lamps ${run}`;
  const troupeId = (await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle })).id;
  await backstoryOptional(custodian.page, troupeId);
  const otherId = (await send(custodian.page, "POST", "/api/troupes", { name: `Court of Far Lamps ${run}`, lead_handle: lead.handle })).id;
  await backstoryOptional(custodian.page, otherId);
  // A Brujah built through the API and accepted home in `home`.
  const build = async (page: Page, name: string, home: string): Promise<string> => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
      disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
    };
    for (const [category, chosen] of Object.entries(picks))
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: chosen.map(([name, rating]) => ({ name, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`, {});
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: home });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});
    return id;
  };

  // Mireille is at home here, mid-game and in an open cycle; Tobias, at home in
  // another troupe, visits.
  const mireille = await build(player.page, "Mireille", troupeId);
  const tobias = await build(visitor.page, "Tobias", otherId);
  await send(visitor.page, "POST", `/api/characters/${tobias}/troupes`, { troupe_id: troupeId });
  const tap = { id: crypto.randomUUID(), happened_at: new Date().toISOString(), kind: "change", tracker: "blood", amount: -1 };
  await send(player.page, "POST", `/api/characters/${mireille}/play/taps`, { taps: [tap] });
  const day = 24 * 60 * 60 * 1000;
  const cycle = await send(lead.page, "POST", `/api/troupes/${troupeId}/cycles`, {
    name: "Lamplight",
    closes_at: new Date(Date.now() + 7 * day).toISOString(),
    grace_ends_at: new Date(Date.now() + 14 * day).toISOString(),
  });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/open`, {});

  // The lead archives it from the Profile tab, seeing first what that settles.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/profile`);
  await l.getByRole("button", { name: "Archive troupe…" }).click();
  const dialog = l.getByRole("dialog", { name: `Archive ${troupeName}` });
  await expect(dialog.getByText("leave these characters with no home troupe: Mireille (closing-player)")).toBeVisible();
  await expect(dialog.getByText("end these characters' visits: Tobias (closing-visit)")).toBeVisible();
  await expect(dialog.getByText("end the open downtime cycle, Lamplight, without answering or delivering it")).toBeVisible();
  await expect(dialog.getByText(/end the games under way .*: Mireille/)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Archive troupe" })).toBeDisabled();
  await dialog.getByLabel("Reason").fill("The chronicle has ended");
  await l.screenshot(shots("archive-troupe"));
  await dialog.getByRole("button", { name: "Archive troupe" }).click();
  await expect(l).toHaveURL(/\/troupes$/);
  await expect(l.locator("main").getByRole("link", { name: troupeName })).toHaveCount(0);

  // Both players are told; Mireille has no home troupe now and Tobias still has his.
  const p = player.page;
  await p.reload();
  await p.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(p.getByText(`${troupeName} is archived (The chronicle has ended): Mireille has no home troupe now`, { exact: false })).toBeVisible();
  await p.keyboard.press("Escape");
  const memberships = await p.request.get(`/api/characters/${mireille}/troupes`, { headers });
  expect(await memberships.json()).toEqual([]);
  await visitor.page.reload();
  await visitor.page.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(visitor.page.getByText(`${troupeName} is archived (The chronicle has ended): Tobias no longer visits it`)).toBeVisible();

  // The custodian finds it under Archived troupes, with who archived it, why, and
  // the characters it had; its log is still there to read.
  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "Archived troupes" }).click();
  const card = c.getByRole("listitem").filter({ has: c.getByRole("heading", { name: troupeName }) });
  await expect(card.getByText("The chronicle has ended")).toBeVisible();
  await expect(card.getByRole("link", { name: "closing-lead" })).toBeVisible();
  await expect(card.getByRole("link", { name: "Mireille" })).toBeVisible();
  await expect(card.getByRole("link", { name: "Tobias" })).toBeVisible();
  await c.screenshot(shots("archived-troupes"));
  await card.getByRole("link", { name: "Log", exact: true }).click();
  await expect(c.getByText("closing-lead archived the troupe (The chronicle has ended).")).toBeVisible();
  await expect(c.getByText("closing-lead ended the downtime cycle Lamplight unanswered, as the troupe was archived.")).toBeVisible();

  // Reopened, it is running again, but Mireille does not come back by herself.
  await c.goBack();
  await card.getByRole("button", { name: "Reopen…" }).click();
  const reopen = c.getByRole("dialog", { name: `Reopen ${troupeName}` });
  await reopen.getByLabel("Reason").fill("A new chronicle");
  await reopen.getByRole("button", { name: "Reopen troupe" }).click();
  await expect(c.getByRole("heading", { name: troupeName })).toHaveCount(0);
  await l.goto(`/troupes/${troupeId}`);
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  expect(await (await p.request.get(`/api/characters/${mireille}/troupes`, { headers })).json()).toEqual([]);
});

test("a lead adds staff by picking from a list of people, the troupe's own players first", async ({ browser }) => {
  const custodian = await person(browser, "staff-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "staff-lead");
  const player = await person(browser, "staff-player");
  const troupeName = `Court of Keys ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  // The custodian finds the lead in the list by typing part of their handle.
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle.slice(0, -2));
  await custodian.page.getByRole("listbox", { name: "People" }).getByRole("option", { name: `@${lead.handle}` }).click();
  await expect(custodian.page.getByLabel("Lead storyteller")).toHaveValue(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // The player's character visits the troupe.
  const p = player.page;
  await p.getByLabel("Name").fill("Agnes Moreau");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  await characterTab(p, "Troupes");
  await p.getByLabel("Troupe to join").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Visit", exact: true }).click();
  await expect(p.getByRole("listitem").filter({ hasText: troupeName })).toBeVisible();
  // Home troupe comes first, then the visiting troupes, each with what it means behind its (i).
  await expect(p.locator("main section h2")).toHaveText(["Home troupe", "Visiting troupes"]);
  const card = (title: string) => p.locator("main section").filter({ has: p.getByRole("heading", { name: title }) });
  await expect(card("Home troupe").getByText("The one troupe that holds this character's sheet.")).toHaveCount(0);
  await card("Home troupe").getByRole("button", { name: "What a home troupe is" }).click();
  await expect(card("Home troupe").getByText("The one troupe that holds this character's sheet.")).toBeVisible();
  // Closed again first: on a phone it covers the next card's (i).
  await p.keyboard.press("Escape");
  await card("Visiting troupes").getByRole("button", { name: "What a visiting troupe is" }).click();
  await expect(card("Visiting troupes").getByText("A troupe this character plays in without its home there.")).toBeVisible();

  // The list opens as soon as the box is clicked: the troupe's player first.
  await lead.page.getByRole("link", { name: "Troupes" }).click();
  await lead.page.getByRole("link", { name: troupeName }).click();
  await lead.page.getByRole("link", { name: "Staff", exact: true }).click();
  await lead.page.getByLabel("Person").click();
  const people = lead.page.getByRole("listbox", { name: "People" });
  await expect(people.getByRole("option").first()).toContainText(`@${player.handle}`);
  await expect(people.getByRole("option").first()).toContainText("Plays here");
  await expect(people).not.toContainText("@example.com");
  await lead.page.screenshot(shots("staff-picker"));
  await people.getByRole("option", { name: `@${player.handle}` }).click();
  await expect(lead.page.getByLabel("Person")).toHaveValue(player.handle);
  // Each role says in a line what it may do.
  const roles = lead.page.locator("section").filter({ has: lead.page.getByRole("heading", { name: "Roles", exact: true }) });
  await expect(roles.getByText("Never sees character sheets.")).toBeVisible();
  await expect(roles.getByText(/^Everything a storyteller does except manage staff/)).toBeVisible();
  await lead.page.getByRole("button", { name: "Add to staff" }).click();
  await expect(lead.page.getByText(`@${player.handle} · Narrator`)).toBeVisible();

  // Now on the staff, they are greyed out with their role.
  await lead.page.getByLabel("Person").click();
  const added = people.getByRole("option", { name: `@${player.handle}` });
  await expect(added).toHaveAttribute("aria-disabled", "true");
  await expect(added).toContainText("Narrator");
  // So is the lead.
  await lead.page.getByLabel("Person").fill(lead.handle);
  await expect(people.getByRole("option", { name: `@${lead.handle}` })).toHaveAttribute("aria-disabled", "true");
  await expect(people.getByRole("option", { name: `@${lead.handle}` })).toContainText("Lead storyteller");
  await lead.page.keyboard.press("Escape");

  // Their role is changed in the staff list.
  await lead.page.getByLabel("Role for staff-player").selectOption("assistant_storyteller");
  await expect(lead.page.getByText(`@${player.handle} · Assistant storyteller`)).toBeVisible();
});

test("a new player goes from a troupe's page to building a character for it, the troupe already chosen", async ({ browser }) => {
  const custodian = await person(browser, "playhere-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "playhere-lead");
  const player = await person(browser, "playhere-new");
  const troupeName = `Court of Open Doors ${run}`;
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // A new player is welcomed with the steps to a first game; staff, with no characters either, land on their troupes.
  const p = player.page;
  await expect(p.getByRole("heading", { name: "Welcome to Horatio" })).toBeVisible();
  await lead.page.reload();
  await expect(lead.page.getByRole("heading", { name: "Your troupes" })).toBeVisible();
  await expect(lead.page.getByText("No characters of your own yet.", { exact: false })).toBeVisible();
  await expect(lead.page.getByRole("heading", { name: "Welcome to Horatio" })).toHaveCount(0);

  // The troupe's page says how to play there: one click to a character built for it.
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByRole("heading", { name: "Play here" })).toBeVisible();
  await p.screenshot(shots("play-here"));
  await p.getByRole("link", { name: `Build a new character for ${troupeName}` }).click();
  await expect(p).toHaveURL(new RegExp(`/characters\\?troupe=${troupeId}`));
  await expect(p.getByLabel("Which troupe will you play in?")).toHaveValue(troupeId);
  await expect(p.getByText(`Your troupe: ${troupeName}`)).toBeVisible();
  await p.screenshot(shots("welcome"));

  // Its staff see no such card.
  await lead.page.goto(`/troupes/${troupeId}`);
  await expect(lead.page.getByRole("heading", { level: 1 })).toContainText(troupeName);
  await expect(lead.page.getByRole("heading", { name: "Play here" })).toHaveCount(0);
});

test("a player brings a character they have to a troupe from its page, and is told it waits for the storytellers", async ({ browser }) => {
  const custodian = await person(browser, "bringer-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bringer-lead");
  const player = await person(browser, "bringer-player");
  const troupeName = `Court of Second Chances ${run}`;
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  await backstoryOptional(custodian.page, troupeId);
  const p = player.page;
  await builtVampire(p, "Ottoline", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });

  // "Ask to join" opens the character's Troupes tab with this troupe chosen.
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByRole("heading", { name: "Play here" })).toBeVisible();
  await p.getByRole("listitem").filter({ hasText: "Ottoline" }).getByRole("link", { name: "Ask to join" }).click();
  await expect(p.getByRole("combobox", { name: "Troupe", exact: true })).toHaveValue(troupeId);
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(`Waiting for ${troupeName}'s storytellers to accept this character.`)).toBeVisible();

  // Back on the troupe's page, the card says so instead.
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByRole("heading", { name: "Waiting for the storytellers" })).toBeVisible();
  await expect(p.getByRole("link", { name: `Build a new character for ${troupeName}` })).toHaveCount(0);
});

test("the characters list and each Troupes tab say where a character stands: in creation, waiting, at home, or with no home yet (#368)", async ({ browser }) => {
  const custodian = await person(browser, "whereami-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "whereami-lead");
  const player = await person(browser, "whereami-play");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "GET" | "POST" | "PUT", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data: method === "GET" ? undefined : (data ?? {}) });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const hearths = `Court of Hearths ${run}`;
  const farShores = `Court of Far Shores ${run}`;
  const home = await send(custodian.page, "POST", "/api/troupes", { name: hearths, lead_handle: lead.handle });
  const away = await send(custodian.page, "POST", "/api/troupes", { name: farShores, lead_handle: lead.handle });
  for (const t of [home, away]) await backstoryOptional(custodian.page, t.id);
  const p = player.page;
  // Characters made through the API: one left in creation, three finished.
  const make = async (name: string, finish: boolean) => {
    const { id } = await send(p, "POST", "/api/characters", { splat: "vampire", name, building_troupe_id: home.id });
    if (!finish) return id as string;
    await send(p, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
      disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
    };
    for (const [category, list] of Object.entries(picks))
      await send(p, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send(p, "POST", `/api/characters/${id}/creation/complete`);
    return id as string;
  };
  const halfway = await make("Halfway Hester", false);
  const asker = await make("Asking Aldous", true);
  const settled = await make("Settled Seraphine", true);
  const loner = await make("Lone Lucan", true);
  await send(p, "POST", `/api/characters/${asker}/home-troupe`, { troupe_id: away.id });
  const asked = await send(p, "POST", `/api/characters/${settled}/home-troupe`, { troupe_id: home.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  const now = Date.now();
  const cycle = await send(lead.page, "POST", `/api/troupes/${home.id}/cycles`, {
    name: "Hearth month",
    closes_at: new Date(now + 7 * 86400e3).toISOString(),
    grace_ends_at: new Date(now + 9 * 86400e3).toISOString(),
  });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/open`);

  // The list says where each stands, and the downtime due.
  const row = (name: string) => p.getByRole("listitem").filter({ hasText: name });
  await p.goto("/characters");
  await expect(row("Halfway Hester")).toContainText("In creation");
  await expect(row("Asking Aldous")).toContainText(`Waiting for ${farShores}`);
  await expect(row("Settled Seraphine")).toContainText(`Home: ${hearths}`);
  await expect(row("Settled Seraphine").getByText(/^Downtime due \w{3} /)).toBeVisible();
  await expect(row("Lone Lucan")).toContainText("No home troupe yet");
  await expect(p.getByText("Active", { exact: true })).toHaveCount(0);
  await p.screenshot(shots("characters-standing"));

  // Submitted and answered, the results are new until the player opens them.
  const form = await send(p, "GET", `/api/characters/${settled}/downtime`);
  const question = form.questions.find((q: { prompt: string }) => q.prompt === "Downtime action");
  await send(p, "PUT", `/api/characters/${settled}/downtime/answers`, { answers: [{ question_id: question.id, slot: 1, body: "Tend the hearth." }] });
  await send(p, "POST", `/api/characters/${settled}/downtime/submit`);
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/close`, { add_to_ceiling: true });
  const [response] = await send(lead.page, "GET", `/api/cycles/${cycle.id}/responses`);
  await send(lead.page, "PUT", `/api/responses/${response.id}`, { body: "The fire holds." });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/deliver`, { partial: true });
  await p.reload();
  await expect(row("Settled Seraphine")).toContainText("New results");
  await expect(row("Settled Seraphine")).not.toContainText("Downtime due");
  await p.goto(`/characters/${settled}`);
  await characterTab(p, "Results");
  await expect(p.getByText("The fire holds.")).toBeVisible();
  await p.goto("/characters");
  await expect(row("Settled Seraphine")).toContainText(`Home: ${hearths}`);
  await expect(row("Settled Seraphine")).not.toContainText("New results");

  // Each Troupes tab opens with the home troupe, or says there is none yet and how to get one.
  const homeCard = p.locator("main section").filter({ has: p.getByRole("heading", { name: "Home troupe" }) });
  await p.goto(`/characters/${settled}/troupes`);
  await expect(homeCard).toContainText(`Home now: ${hearths}`);
  await expect(homeCard.getByRole("link", { name: `${hearths}'s house rules` })).toBeVisible();
  await p.screenshot(shots("troupes-home"));
  await expect(homeCard.getByRole("combobox")).toHaveCount(0);
  await homeCard.getByRole("button", { name: "Move to another troupe…" }).click();
  await expect(homeCard.getByRole("combobox", { name: "New home troupe" })).toBeVisible();

  await p.goto(`/characters/${asker}/troupes`);
  await expect(homeCard).toContainText("No home troupe yet");
  await expect(homeCard).toContainText(`Waiting for ${farShores}'s storytellers to accept this character.`);
  await expect(homeCard).toContainText("Nothing for you to do until they decide.");

  await p.goto(`/characters/${loner}/troupes`);
  await expect(homeCard).toContainText("No home troupe yet");
  await expect(homeCard.getByRole("combobox", { name: "Troupe", exact: true })).toBeVisible();

  await p.goto(`/characters/${halfway}/troupes`);
  await expect(homeCard).toContainText("No home troupe yet");
  await expect(homeCard).toContainText(`then ask ${hearths} here`);
  await homeCard.getByRole("link", { name: "Create tab" }).click();
  await expect(p).toHaveURL(new RegExp(`/characters/${halfway}/create`));
});

test("a troupe's profile: storytellers fill it in, and people not signed in see it only when it is public", async ({ browser }) => {
  test.slow();
  const custodian = await person(browser, "profile-custodian");
  makeCustodian(custodian.email);
  // The lead plans games in New York; a visitor reads them in Tokyo.
  const lead = await person(browser, "profile-lead", { timezoneId: "America/New_York" });
  const player = await person(browser, "profile-player");
  const visitor = await (await browser.newContext({ timezoneId: "Asia/Tokyo" })).newPage();
  const troupeName = `Lords of Leeds ${run}`;

  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Troupes" }).click();
  await expect(c.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await c.getByLabel("Name").fill(troupeName);
  await c.getByLabel("Lead storyteller").fill(lead.handle);
  await c.getByRole("button", { name: "Create troupe" }).click();
  await expect(c.getByRole("link", { name: troupeName })).toBeVisible();

  // The lead fills in the profile on the troupe's Profile tab.
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  const troupeUrl = l.url();
  const troupeId = troupeUrl.split("/troupes/")[1]!.split("/")[0]!;
  await l.getByRole("link", { name: "Profile", exact: true }).click();
  await l.getByRole("button", { name: "Edit profile" }).click();
  // A portrait, cropped square like a character's picture.
  await l.getByRole("button", { name: "Add a portrait" }).click();
  await l.getByLabel("Choose a portrait").setInputFiles("e2e/portrait.jpg");
  await expect(l.getByRole("slider", { name: /Where the portrait is/ })).toBeVisible();
  await l.getByRole("button", { name: "Save picture" }).click();
  await expect(l.getByRole("dialog")).toBeHidden();
  await l.getByLabel("Website").fill("https://lords.example.org");
  await l.getByLabel("Discord invite").fill("https://discord.gg/lords");
  await l.getByLabel("How often games run").fill("Second Saturday of the month, 7 pm to midnight");
  // A game: its end starts five hours on.
  await l.getByLabel("Game starts").fill("2030-01-12T19:00");
  await expect(l.getByLabel("Game ends")).toHaveValue("2030-01-13T00:00");
  // The browser draws each input in its own order; under it, the date the app's way.
  await expect(l.getByText("Sat 12 Jan 2030, 7:00 pm EST")).toBeVisible();
  await expect(l.getByText("Sun 13 Jan 2030, 12:00 am EST")).toBeVisible();
  await l.getByRole("button", { name: "Add game" }).click();
  await expect(l.getByRole("list", { name: "Upcoming games to edit" }).getByText("Sat 12 Jan 2030, 7 pm to Sun 13 Jan 2030, 12 am EST")).toBeVisible();
  await l.getByLabel("City or region").fill("Leeds");
  await l.getByLabel("Venue name").fill("The Crypt");
  await l.getByLabel("Address", { exact: true }).fill("12 Mill Lane, Leeds");
  await l.getByLabel("Accessibility").fill("Step-free access and a quiet room.");
  await l.getByLabel("Chronicle").fill("Leeds by Night");
  await l.getByLabel("Era").fill("Modern nights");
  await l.getByLabel("Tone").fill("Slow-burning political horror.");
  await l.getByLabel("Taking new players?").selectOption({ label: "Welcoming new players" });
  await l.getByLabel("Contact for new players").selectOption({ label: `profile-lead (@${lead.handle})` });
  await l.getByLabel("Minimum age").fill("18");
  await l.getByLabel("Content notes").fill("Violence and body horror.");
  await l.screenshot(shots("troupe-profile-edit"));
  await l.getByRole("button", { name: "Save profile" }).click();

  // It shows on the troupe page, with the next game in the lead's own zone.
  await expect(l.getByText("Sat 12 Jan 2030, 7 pm EST")).toBeVisible();
  await expect(l.getByText("Welcoming new players")).toBeVisible();
  await expect(l.getByText("12 Mill Lane, Leeds")).toBeVisible();
  await expect(l.getByText("18+")).toBeVisible();
  const website = l.getByRole("link", { name: "Website" });
  await expect(website).toHaveAttribute("href", "https://lords.example.org");
  await expect(website).toHaveAttribute("target", "_blank");
  await expect(l.getByRole("heading", { level: 1 }).locator('img[src*="/portraits/"]')).toBeVisible();
  await l.screenshot(shots("troupe-profile"));

  // Anyone signed in sees it, street address and all; and the portrait shows in the troupe list.
  const p = player.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await expect(p.getByRole("link", { name: troupeName }).locator('img[src*="/portraits/"]')).toBeVisible();
  await p.getByRole("link", { name: troupeName }).click();
  await p.getByRole("link", { name: "Profile", exact: true }).click();
  await expect(p.getByText("12 Mill Lane, Leeds")).toBeVisible();
  await expect(p.getByRole("button", { name: "Edit profile" })).toHaveCount(0);
  await expect(p.getByRole("switch", { name: "Public" })).toHaveCount(0);

  // Off, as it starts: someone not signed in is told nothing about it.
  await visitor.goto(`/t/${troupeId}`);
  await expect(visitor.getByText(/only for people signed in, or there is no such troupe/)).toBeVisible();
  await expect(visitor.getByText(troupeName)).toHaveCount(0);

  // Switched on: anyone can see it at its public address, but never the street address.
  await l.getByRole("switch", { name: "Public" }).click();
  await expect(l.getByText("Public: anyone can see this profile, even people not signed in")).toBeVisible();
  await visitor.reload();
  await expect(visitor.getByRole("heading", { name: troupeName })).toBeVisible();
  await expect(visitor.getByText("The Crypt")).toBeVisible();
  await expect(visitor.getByText("to see the address.")).toBeVisible();
  await expect(visitor.getByText("12 Mill Lane")).toHaveCount(0);
  await expect(visitor.getByText(lead.email)).toHaveCount(0);
  await expect(visitor.getByText(`@${lead.handle}`).first()).toBeVisible();
  // The next game, in the visitor's own zone.
  await expect(visitor.getByText("Sun 13 Jan 2030, 9 am GMT+9")).toBeVisible();
  await expect(visitor.locator('img[src*="/portraits/"]').first()).toBeVisible();
  await visitor.screenshot(shots("troupe-profile-public"));
  // A link to it previews with the troupe's name and portrait.
  const shared = await (await visitor.request.get(`/t/${troupeId}`)).text();
  expect(shared).toContain(`<meta property="og:title" content="${troupeName}" />`);
  expect(shared).toMatch(/<meta property="og:image" content="[^"]*\/portraits\/[^"]*\/512\.webp" \/>/);

  // Switched off again, it is for people signed in only once more.
  await l.getByRole("switch", { name: "Public" }).click();
  await expect(l.getByText("Signed-in only")).toBeVisible();
  await visitor.reload();
  await expect(visitor.getByText(/only for people signed in, or there is no such troupe/)).toBeVisible();
});

test("members say whether they are coming to a game, staff see who, and a calendar link can be reset", async ({ browser }) => {
  const custodian = await person(browser, "rsvp-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "rsvp-lead", { timezoneId: "Europe/London" });
  const player = await person(browser, "rsvp-player", { timezoneId: "Europe/London" });
  const troupeName = `Lanterns of Lincoln ${run}`;
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await send(lead.page, "POST", `/api/troupes/${troupeId}/games`, { starts_at: "2030-03-09T19:00:00Z", ends_at: "2030-03-10T00:00:00Z" });
  // Rosalind visits the troupe, which makes her player a member.
  const { id: rosalind } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: "Rosalind" });
  await send(player.page, "POST", `/api/characters/${rosalind}/troupes`, { troupe_id: troupeId });

  // The player says she's coming, on the troupe's About tab.
  const p = player.page;
  await p.goto(`/troupes/${troupeId}`);
  const game = p.getByRole("list", { name: "Games to come" }).getByRole("listitem").filter({ hasText: "Sat 9 Mar 2030, 7 pm" });
  await expect(game.getByText("No answers yet")).toBeVisible();
  const choices = game.getByRole("group", { name: /^Are you coming on Sat 9 Mar 2030, 7 pm GMT/ });
  await choices.getByRole("button", { name: "Coming", exact: true }).click();
  await expect(p.getByText(/^Coming: Sat 9 Mar 2030, 7 pm GMT/)).toBeVisible();
  await expect(choices.getByRole("button", { name: "Coming", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(game.getByText("1 coming")).toBeVisible();
  // Players see how many, not who.
  await expect(game.getByText("See who answered")).toHaveCount(0);
  await p.screenshot(shots("troupe-games-rsvp"));

  // The lead sees who is coming, with the character she plays here.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}`);
  const leadGame = l.getByRole("list", { name: "Games to come" }).getByRole("listitem").filter({ hasText: "Sat 9 Mar 2030, 7 pm" });
  await expect(leadGame.getByText("1 coming")).toBeVisible();
  await leadGame.getByText("See who answered").click();
  await expect(leadGame.getByRole("list", { name: "Coming" })).toContainText("rsvp-player");
  await expect(leadGame.getByRole("list", { name: "Coming" })).toContainText("Rosalind");
  await l.screenshot(shots("troupe-games-staff"));

  // She changes her mind: one answer per person.
  await choices.getByRole("button", { name: "Maybe" }).click();
  await expect(game.getByText("1 maybe")).toBeVisible();
  await expect(choices.getByRole("button", { name: "Coming", exact: true })).toHaveAttribute("aria-pressed", "false");

  // Her calendar link: the feed has the game, and resetting it stops the old one.
  await p.getByRole("button", { name: "Subscribe to the calendar" }).click();
  const dialog = p.getByRole("dialog", { name: "Subscribe to the calendar" });
  const only = dialog.getByRole("region", { name: `${troupeName} only` });
  await only.getByRole("button", { name: "Get the link" }).click();
  const address = only.locator(".font-mono");
  await expect(address).toHaveText(/\/api\/calendar\/[\w-]+\.ics$/);
  await expect(only.getByRole("link", { name: "Open in your calendar app" })).toHaveAttribute("href", /^webcal:\/\//);
  await expect(dialog.getByText("Google Calendar")).toBeVisible();
  await p.screenshot(shots("troupe-calendar-subscribe"));
  const path = (url: string) => url.slice(url.indexOf("/api/"));
  const old = path((await address.textContent())!);
  const feed = await p.request.get(old);
  expect(feed.status()).toBe(200);
  expect(feed.headers()["content-type"]).toContain("text/calendar");
  const ics = await feed.text();
  expect(ics).toContain("BEGIN:VCALENDAR");
  expect(ics).toContain(`SUMMARY:Game: ${troupeName}`);
  expect(ics).toContain("DTSTART:20300309T190000Z");
  expect(ics).not.toContain(player.email);
  await only.getByRole("button", { name: "Reset the link…" }).click();
  await only.getByRole("button", { name: "Reset the link", exact: true }).click();
  await expect(only.getByRole("status")).toHaveText("New link made. The old one no longer works.");
  await expect(address).not.toHaveText(new RegExp(old.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  expect((await p.request.get(old)).status()).toBe(404);
  expect((await p.request.get(path((await address.textContent())!))).status()).toBe(200);
});

test("players check in at the door and land in their Play View, and staff award the game's XP to those who came", async ({ browser }) => {
  const custodian = await person(browser, "door-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "door-lead");
  const player = await person(browser, "door-player");
  const troupeName = `Keepers of Kendal ${run}`;
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupeId);
  // A game under way: it started an hour ago.
  const start = new Date(Date.now() - 60 * 60_000);
  await send(lead.page, "POST", `/api/troupes/${troupeId}/games`, { starts_at: start.toISOString(), ends_at: new Date(start.getTime() + 5 * 60 * 60_000).toISOString() });
  // Hester is at home in the troupe, with 7 XP already this month; Wilf only visits.
  const { id: hester } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: "Hester" });
  await send(player.page, "PUT", `/api/characters/${hester}/traits`, { category: "clan", name: "Brujah", rating: null });
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
    await send(player.page, "PUT", `/api/characters/${hester}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
  await send(player.page, "POST", `/api/characters/${hester}/creation/complete`);
  const asked = await send(player.page, "POST", `/api/characters/${hester}/home-troupe`, { troupe_id: troupeId });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  await send(lead.page, "POST", `/api/characters/${hester}/xp`, { amount: 7, reason: "Game, earlier this month" });
  const { id: wilf } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: "Wilf" });
  await send(player.page, "POST", `/api/characters/${wilf}/troupes`, { troupe_id: troupeId });

  // The lead opens check-in from the game on About: a code and a QR code for the door.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}`);
  const leadGame = l.getByRole("list", { name: "Games to come" }).getByRole("listitem").first();
  await expect(leadGame.getByText("Nobody checked in yet")).toBeVisible();
  await leadGame.getByRole("link", { name: "Check-in and attendance" }).click();
  await expect(l.getByRole("heading", { name: "Game night" })).toBeVisible();
  await expect(l.getByText("Nobody has checked in yet.")).toBeVisible();
  await l.getByRole("button", { name: "Open check-in" }).click();
  await expect(l.getByText("Check-in is open.")).toBeVisible();
  await expect(l.getByRole("img", { name: /^QR code for check-in/ })).toBeVisible();
  const code = ((await l.getByLabel(/^Code /).textContent()) ?? "").replace(/\s/g, "");
  expect(code).toMatch(/^[A-Z2-9]{6}$/);
  await l.screenshot(shots("game-night-door"));
  await l.getByRole("button", { name: "Show at the door" }).click();
  await expect(l.getByRole("dialog", { name: "Check in" }).getByRole("img", { name: /^QR code for check-in/ })).toBeVisible();
  await l.screenshot(shots("game-night-door-shown"));
  await l.getByRole("dialog", { name: "Check in" }).getByRole("button", { name: "Close" }).last().click();

  // The QR code's link, followed signed out, signs the player in and comes back.
  const door = await (await browser.newContext()).newPage();
  await door.goto(`/check-in/${code}`);
  await expect(door.getByRole("heading", { name: "Sign in" })).toBeVisible();
  expect(new URL(door.url()).searchParams.get("next")).toBe(`/check-in/${code}`);
  await door.getByLabel("Email or handle").fill(player.email);
  await door.getByLabel("Password").fill(PASSWORD);
  await door.getByRole("button", { name: "Sign in" }).click();
  await expect(door.getByRole("heading", { name: "Check in" })).toBeVisible();
  await expect(door.getByText(troupeName)).toBeVisible();
  await door.getByLabel("Hester").check();
  await door.screenshot(shots("check-in"));
  await door.getByRole("button", { name: "Check in Hester" }).click();
  // Her night starts on the Play View.
  await expect(door.getByRole("heading", { name: "Hester" })).toBeVisible();
  expect(new URL(door.url()).pathname).toBe(`/play/characters/${hester}`);

  // Wilf, from the game on About, without the code; no day's rest for him.
  const p = player.page;
  await p.goto(`/troupes/${troupeId}`);
  const game = p.getByRole("list", { name: "Games to come" }).getByRole("listitem").first();
  await expect(game.getByText("Checked in: Hester")).toBeVisible();
  await game.getByRole("button", { name: "Check in" }).click();
  const dialog = p.getByRole("dialog", { name: /^Check in: / });
  await expect(dialog).toContainText("Hester · checked in");
  await dialog.getByLabel("A full day's rest since the last game").uncheck();
  await dialog.getByRole("button", { name: "Check in Wilf" }).click();
  await expect(p.getByRole("heading", { name: "Wilf" })).toBeVisible();

  // The lead sees who came, checks Wilf out and back in by hand.
  await l.reload();
  const came = l.getByRole("list", { name: "Checked in" });
  await expect(l.getByRole("heading", { name: "Who came (2)" })).toBeVisible();
  const wilfRow = came.getByRole("listitem").filter({ hasText: "Wilf" });
  await expect(wilfRow.getByText("Visiting")).toBeVisible();
  await expect(wilfRow.getByText("No day's rest")).toBeVisible();
  await wilfRow.getByRole("button", { name: "Check out Wilf" }).click();
  await expect(l.getByText("Checked out: Wilf")).toBeVisible();
  await expect(came.getByRole("listitem")).toHaveCount(1);
  await l.getByLabel("Check someone in by hand").selectOption({ label: "Wilf (door-player)" });
  await l.getByRole("button", { name: "Check in", exact: true }).click();
  await expect(l.getByText("Checked in: Wilf")).toBeVisible();
  await expect(came.getByRole("listitem").filter({ hasText: "Wilf" }).getByText("By hand")).toBeVisible();

  // The game's XP to those who came: the book's guidance, and a warning, not a refusal, past 10 in the month.
  await expect(l.getByText("The book suggests 3 to 5 XP a game, and no more than 8 to 10 a month (MET: VtM core, p. 108).")).toBeVisible();
  await expect(l.getByText("Wilf visiting: their home troupes award their XP.")).toBeVisible();
  await expect(l.getByRole("alert")).toHaveText("This takes Hester past 10 XP this month, more than the book suggests. You can still award it.");
  await l.getByRole("button", { name: "Less XP for the game" }).click();
  await l.getByRole("button", { name: "Award…" }).click();
  await l.screenshot(shots("game-night-award"));
  await l.getByRole("button", { name: "Yes, award 7 XP to 1 character" }).click();
  await expect(l.getByText("Awarded 7 XP to 1 character. Hester now has more than 10 this month.")).toBeVisible();
  await expect(l.getByText(/^7 XP awarded to everyone here who calls this troupe home/)).toBeVisible();
  await expect(l.getByText("Check-in closed when the game's XP was awarded.")).toBeVisible();

  // Hester's Experience tab has the award and the game she came to.
  await p.goto(`/characters/${hester}`);
  await characterTab(p, "Experience");
  await expect(p.getByRole("cell", { name: /^Game, / }).first()).toBeVisible();
  await expect(p.getByRole("heading", { name: "Games attended (1)" })).toBeVisible();
  await expect(p.getByRole("list", { name: "Games attended" })).toContainText(troupeName);
});

test("a troupe's public page asks a newcomer to make an account, which brings them back to the troupe", async ({ browser }) => {
  const custodian = await person(browser, "joinlink-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "joinlink-lead");
  const troupeName = `Wardens of Whitby ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;
  const next = encodeURIComponent(`/troupes/${troupeId}`);

  // Signed-in only, the page still offers a way in.
  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto(`/t/${troupeId}`);
  await expect(visitor.getByText(/only for people signed in, or there is no such troupe/)).toBeVisible();
  await expect(visitor.getByRole("link", { name: "Create an account to play here" })).toHaveAttribute("href", `/sign-up?next=${next}`);
  await expect(visitor.getByRole("link", { name: "Sign in", exact: true })).toHaveAttribute("href", `/sign-in?next=${next}`);
  await visitor.screenshot(shots("anon-private-troupe"));

  // Public, the troupe's name leads, with the same two ways in.
  await l.getByRole("link", { name: "Profile", exact: true }).click();
  await l.getByRole("switch", { name: "Public" }).click();
  await expect(l.getByRole("switch", { name: "Public" })).toBeChecked();
  await visitor.reload();
  await expect(visitor.getByRole("heading", { name: troupeName })).toBeVisible();
  await expect(visitor.getByRole("link", { name: "Sign in", exact: true })).toHaveAttribute("href", `/sign-in?next=${next}`);
  await visitor.screenshot(shots("anon-public-troupe"));

  // They make an account, and land on the troupe's own page.
  await visitor.getByRole("link", { name: "Create an account to play here" }).click();
  await expect(visitor.getByRole("heading", { name: "Create an account" })).toBeVisible();
  await expect(visitor.getByText("Character sheets and downtimes for Mind's Eye Theatre troupes.")).toBeVisible();
  await visitor.screenshot(shots("signup"));
  await visitor.getByLabel("Your name").fill("joinlink-newcomer");
  await visitor.getByLabel("Handle").fill(`joinlink_${run.slice(-10)}`);
  await visitor.getByLabel("Email").fill(`joinlink-newcomer-${run}@example.com`);
  await visitor.getByLabel("Password").fill("a long enough password");
  await visitor.getByRole("button", { name: "Create account" }).click();
  await expect(visitor.getByRole("heading", { name: troupeName })).toBeVisible();
  await expect(visitor).toHaveURL(new RegExp(`/troupes/${troupeId}$`));
});

test("a troupe's Profile tab switches it public at once, About shows its XP range, and Waiting on you leads to the work", async ({ browser }) => {
  const custodian = await person(browser, "tidy-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tidy-lead");
  const player = await person(browser, "tidy-player");
  const visitor = await (await browser.newContext()).newPage();
  const troupeName = `Court of Thresholds ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  await backstoryOptional(custodian.page, troupeName);

  // About, for the lead: nothing is waiting yet.
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;
  const waiting = l.locator("section").filter({ has: l.getByRole("heading", { name: "Waiting on you" }) });
  await expect(waiting.getByText("Nothing waiting.")).toBeVisible();

  // Profile: the Public switch saves as soon as it is changed.
  await l.getByRole("link", { name: "Profile", exact: true }).click();
  const publicSwitch = l.getByRole("switch", { name: "Public" });
  await expect(publicSwitch).not.toBeChecked();
  await expect(l.getByText("Signed-in only")).toBeVisible();
  await visitor.goto(`/t/${troupeId}`);
  await expect(visitor.getByText(/only for people signed in, or there is no such troupe/)).toBeVisible();
  await publicSwitch.click();
  await expect(publicSwitch).toBeChecked();
  await expect(l.getByText("Public: anyone can see this profile, even people not signed in")).toBeVisible();
  await expect(l.getByText(`/t/${troupeId}`)).toBeVisible();
  await l.reload();
  await expect(l.getByRole("switch", { name: "Public" })).toBeChecked();
  await visitor.reload();
  await expect(visitor.getByRole("heading", { name: troupeName })).toBeVisible();
  // The lead's name and description are here too, and archiving under its own heading.
  await l.getByLabel("Description").fill("A court that meets where the roads cross.");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByRole("region", { name: "Profile" }).getByText("A court that meets where the roads cross.")).toBeVisible();
  await expect(l.getByRole("heading", { name: "Archive the troupe" })).toBeVisible();
  await l.screenshot(shots("troupe-profile-tab"));

  // About is to read: the XP floor and ceiling with Award XP beside them, and no settings.
  await l.getByRole("link", { name: "About", exact: true }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}$`));
  // The Profile tab's form can linger a moment after the URL changes, with the description in it.
  await expect(l.getByRole("textbox", { name: "Description" })).toHaveCount(0);
  await expect(l.getByText("A court that meets where the roads cross.")).toBeVisible();
  await expect(l.locator("main").getByRole("link", { name: "Award XP", exact: true })).toBeVisible();
  await expect(l.getByText("Player characters from any sect may join.")).toBeVisible();
  await expect(l.getByRole("checkbox")).toHaveCount(0);
  await expect(l.getByRole("button", { name: "Set by hand" })).toHaveCount(0);
  // The lead sets them by hand in Customise's Troupe settings, with the rest of the troupe's settings.
  await l.getByRole("link", { name: "Change in Customise" }).first().click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/settings$`));
  for (const group of ["Who may join", "XP", "Status and titles", "At game"]) await expect(l.getByRole("group", { name: group, exact: true })).toBeVisible();
  await l.getByRole("button", { name: "Set by hand" }).click();
  await l.getByLabel("Floor", { exact: true }).fill("60");
  await l.getByLabel("Ceiling", { exact: true }).fill("75");
  await l.getByLabel("Why", { exact: true }).fill("Chronicle began in 2021");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("(30 starting + 30 set by hand)")).toBeVisible();
  await expect(l.getByText("(30 starting + 45 set by hand)")).toBeVisible();
  // Starting points leads there for them, and the log on About has the change.
  await l.goto(`/troupes/${troupeId}/rules/starting`);
  await expect(l.getByRole("heading", { name: "XP floor and ceiling" })).toHaveCount(0);
  await expect(l.getByRole("link", { name: "Troupe settings", exact: true }).last()).toHaveAttribute("href", `/troupes/${troupeId}/settings`);
  await l.goto(`/troupes/${troupeId}`);
  await expect(waiting).toBeVisible();
  await expect(l.getByRole("heading", { name: "Latest in the log" })).toBeVisible();

  // A player asks for the troupe to be their character's home: an approval waits.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Hollis" });
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
  await send("POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });

  // Waiting on you says so, and its line goes straight to Approvals.
  await l.reload();
  const approvals = waiting.getByRole("link", { name: /Approvals waiting/ });
  await expect(approvals).toContainText("1");
  await l.screenshot(shots("troupe-about"));
  await approvals.click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/approvals$`));
  await expect(l.getByText("Hollis").first()).toBeVisible();
  // Approvals comes first of the Characters tabs, with its count; the group itself opens on the roster.
  const characterTabs = l.getByRole("navigation", { name: "Characters", exact: true });
  await expect(characterTabs.getByRole("link").first()).toHaveText(/^Approvals/);
  await expect(characterTabs.getByRole("link", { name: /Approvals/ }).getByLabel("1 waiting")).toBeVisible();
  const sections = l.getByRole("navigation", { name: "Troupe sections" });
  await sections.getByRole("link", { name: /^Characters/ }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/characters$`));
  // The troupe's catalogues are a group of their own.
  await sections.getByRole("link", { name: "World", exact: true }).click();
  await expect(l.getByRole("navigation", { name: "World", exact: true }).getByRole("link")).toHaveText(["Locations", "Equipment", "Shared backgrounds"]);
  // On Hollis's sheet the lead is told whose it is and as whom they look, with the way back.
  await l.goto(`/characters/${id}`);
  const viewing = l.getByLabel("Viewing as staff");
  await expect(viewing).toContainText("Viewing as lead storyteller");
  await expect(viewing.getByRole("link", { name: "tidy-player" })).toBeVisible();
  await viewing.getByRole("link", { name: `back to ${troupeName}` }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/approvals$`));

  // The player sees About without the box, and the XP range only to read.
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByRole("heading", { name: "XP floor and ceiling" })).toBeVisible();
  await expect(p.getByText("60 XP", { exact: true })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Waiting on you" })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Set by hand" })).toHaveCount(0);
});

test("Waiting on you shows the open cycle, a quest request and a backstory waiting, the tabs count them, and staff land on their troupes", async ({ browser }) => {
  const custodian = await person(browser, "bells-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bells-lead");
  const player = await person(browser, "bells-player");
  const troupeName = `Court of Waiting Bells ${run}`;
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  const l = lead.page;
  await send(l, "PUT", `/api/troupes/${troupeId}/backstory-settings`, { mode: "free", required: false });
  await send(l, "PUT", `/api/troupes/${troupeId}/quest-settings`, { enabled: true, requests_per_cycle: 1 });

  // The player's character joins, writes a backstory and asks for a quest; a cycle is open.
  const p = player.page;
  const id = await builtVampire(p, "Ilka Varga", "Toreador", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Auspex", 2], ["Celerity", 1], ["Presence", 1]],
  });
  const asked = await send(p, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  await send(l, "POST", `/api/approvals/${asked.id}/approve`);
  await send(p, "PUT", `/api/characters/${id}/backstory`, { text: "Embraced in a Budapest opera house, 1911.", version: 0 });
  const now = Date.now();
  const cycle = await send(l, "POST", `/api/troupes/${troupeId}/cycles`, {
    name: "November downtime",
    closes_at: new Date(now + 7 * 86400e3).toISOString(),
    grace_ends_at: new Date(now + 9 * 86400e3).toISOString(),
  });
  await send(l, "POST", `/api/cycles/${cycle.id}/open`);
  await send(p, "POST", `/api/characters/${id}/quest-requests`, { objective: "Find the lost libretto", reason: "Her sire wrote it", companions: "" });

  // The lead, with no characters of their own, lands on their troupes, with what waits on them in each.
  await l.goto("/");
  await expect(l.getByRole("heading", { name: "Your troupes" })).toBeVisible();
  const home = l.getByRole("list", { name: `Waiting on you in ${troupeName}` });
  await expect(home.getByRole("link", { name: /^November downtime: 0 of 1 submitted · due in \d+ days$/ })).toBeVisible();
  await expect(l.getByRole("link", { name: troupeName }).getByLabel("2 waiting")).toBeVisible();
  await expect(l.getByText("No characters of your own yet.", { exact: false })).toBeVisible();
  await l.screenshot(shots("characters-home-staff"));

  // About's Waiting on you: the open cycle first, then the backstory and the quest request.
  await l.getByRole("link", { name: troupeName }).click();
  const waiting = l.getByRole("list", { name: "Waiting on you" });
  await expect(waiting.getByRole("link")).toHaveText([/^November downtime: 0 of 1 submitted · due in \d+ days$/, /^Backstories to read\s*1$/, /^Quest requests to answer\s*1$/]);
  await l.screenshot(shots("troupe-about-waiting"));
  // The tabs count the same: the backstory on the roster, the request on Quests.
  const sections = l.getByRole("navigation", { name: "Troupe sections" });
  await expect(sections.getByRole("link", { name: /^Characters/ }).getByLabel("1 waiting")).toBeVisible();
  await expect(sections.getByRole("link", { name: /^Downtimes/ }).getByLabel("1 waiting")).toBeVisible();
  await sections.getByRole("link", { name: /^Characters/ }).click();
  const characterTabs = l.getByRole("navigation", { name: "Characters", exact: true });
  await expect(characterTabs.getByRole("link", { name: /^Characters/ }).getByLabel("1 waiting")).toBeVisible();
  // The roster marks the backstory, and the mark opens it.
  await l.getByRole("link", { name: "Backstory to read" }).click();
  await expect(l).toHaveURL(new RegExp(`/characters/${id}/backstory`));
  await expect(l.getByText("Embraced in a Budapest opera house, 1911.")).toBeVisible();
  // The line itself goes straight to the backstory too, and the quest request's to Quests.
  await l.goto(`/troupes/${troupeId}`);
  await waiting.getByRole("link", { name: /^Quest requests to answer/ }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/quests$`));
  await expect(l.getByText("Find the lost libretto")).toBeVisible();
  await expect(sections.getByRole("link", { name: /^Downtimes/ }).getByLabel("1 waiting")).toBeVisible();
});
