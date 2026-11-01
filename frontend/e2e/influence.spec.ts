import { expect, test } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, backstoryOptional, undoInHeader, characterTab } from "./support";

/** Influence: the troupe's log, Gossip, and attacks. */

closeContextsAfterEach();

test("storytellers log influence for PCs, NPCs and names only, and a player reads their character's", async ({ browser }) => {
  // A whole character creation, then a home troupe request.
  test.slow();
  const custodian = await person(browser, "infl-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "infl-lead");
  const player = await person(browser, "infl-player");
  const troupeName = `Court of Ledgers ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  await backstoryOptional(custodian.page, troupeName);

  // The player builds Corvin for the troupe, with Elite 3, and asks to make it home.
  const p = player.page;
  await p.reload();
  await p.getByLabel("Name").fill("Corvin");
  await p.getByLabel("Which troupe will you play in?").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const corvin = new URL(p.url()).pathname.split("/")[2]!;
  await p.getByLabel("Clan").selectOption("Brujah");
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
  await tap("Influences: The Elite 3", "Herd 2", "Generation 1");
  await next("Disciplines");
  await tap("Celerity 2", "Potence 1", "Presence 1");
  await next("Merits & flaws");
  await next("Review");
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  await characterTab(p, "Troupes");
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(/Waiting for .* storytellers/)).toBeVisible();

  // The lead accepts Corvin, keeps an NPC, and opens a cycle.
  const l = lead.page;
  await l.reload();
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;
  await l.goto(`/troupes/${troupeId}/approvals`);
  await l.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();
  const made = await l.request.post(`/api/troupes/${troupeId}/npcs`, { headers: { "X-Horatio": "1" }, data: { name: "Prince Vasquez", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  await l.goto(`/troupes/${troupeId}/downtimes`);
  await expect(l.getByRole("heading", { name: "New cycle" })).toBeVisible();
  await l.getByLabel("Name").fill("December");
  await l.getByRole("button", { name: "Create draft" }).click();
  await l.getByRole("link", { name: "December" }).click();
  await l.getByRole("button", { name: "Open for submissions" }).click();
  await expect(l.getByText("0 of 1 submitted")).toBeVisible();

  // Beside a submission on the cycle page, the tool opens with the character and cycle filled in.
  await l.getByRole("link", { name: "Participants" }).click();
  await l.getByRole("button", { name: "More for Corvin" }).click();
  await l.getByRole("button", { name: "Log influence for Corvin" }).click();
  let form = l.getByRole("dialog").getByRole("form", { name: "Log influence" });
  await expect(form.getByLabel("Who")).toHaveValue("Corvin");
  await expect(form.getByLabel("Applies to this downtime")).toHaveValue(/.+/);
  await form.getByRole("button", { name: "Cancel" }).click();
  await expect(l.getByRole("dialog")).toBeHidden();

  // Corvin's page has nothing logged yet: it says how actions get there, with no filters.
  await l.goto(`/characters/${corvin}/influence`);
  await expect(l.getByText("Corvin has no influence actions logged yet.")).toBeVisible();
  await expect(l.getByText(/shows here once it is logged/)).toBeVisible();
  await expect(l.getByLabel("Findable now (last 90 days)")).toHaveCount(0);

  // From Corvin's page: four times over his Elite 3 for December warns, and logs all the same.
  await l.getByRole("button", { name: "Log influence for Corvin" }).click();
  form = l.getByRole("dialog").getByRole("form", { name: "Log influence" });
  await expect(form.getByLabel("Who")).toHaveValue("Corvin");
  await form.getByLabel("Action").selectOption({ label: "4: Smooth Over" });
  await form.getByLabel("Applies to this downtime").selectOption({ label: "December" });
  await form.getByLabel("Times taken").fill("4");
  await expect(form.getByText("Corvin has 3 Elite actions in December, and this makes 4 logged. You can still log it.")).toBeVisible();
  await form.getByLabel("Purpose").fill("To bury the inspector's report");
  await l.screenshot(shots("log-influence"));
  await form.getByRole("button", { name: "Log it", exact: true }).click();
  await expect(l.getByRole("dialog")).toBeHidden();
  const e1 = l.getByRole("listitem", { name: "Entry E1" });
  await expect(e1.getByText("To bury the inspector's report")).toBeVisible();
  await expect(e1.getByText("taken 4 times")).toBeVisible();
  await expect(e1.getByRole("link", { name: "Logged by staff, for December" })).toBeVisible();

  // On the log page, an NPC's whole month with Add another, dated by the cycle, then a name only.
  await l.goto(`/troupes/${troupeId}/influence`);
  await l.getByRole("button", { name: "Log influence" }).click();
  form = l.getByRole("form", { name: "Log influence" });
  await form.getByLabel("Who").fill("vasq");
  await form.getByRole("option", { name: /Prince Vasquez/ }).click();
  await form.getByLabel("Or date it by").selectOption({ label: "December" });
  await form.getByLabel("Specialisation").selectOption("Finance");
  await form.getByLabel("Action").selectOption({ label: "2: Gossip and Insider Trading" });
  await form.getByLabel("Purpose").fill("To hear who is buying the docks");
  await form.getByRole("button", { name: "Add another" }).click();
  await expect(form.getByText("Logged E2.")).toBeVisible();
  // The date, cycle and who stay; the rest starts again.
  await expect(form.getByLabel("Who")).toHaveValue("Prince Vasquez");
  await expect(form.getByLabel("Applies to this downtime")).toHaveValue(/.+/);
  await expect(form.getByLabel("Purpose")).toHaveValue("");
  await expect(form.getByLabel("Action")).toHaveValue("");
  await form.getByLabel("Action").selectOption({ label: "5: No Party Crashers" });
  await form.getByLabel("Purpose").fill("To keep the Anarchs out of the gala");
  await form.getByRole("button", { name: "Add another" }).click();
  await expect(form.getByText("Logged E3.")).toBeVisible();
  await form.getByLabel("Who").fill("REDACTED");
  await form.getByRole("option", { name: /^REDACTED/ }).click();
  await form.getByLabel("Type").selectOption({ label: "Underworld" });
  await form.getByLabel("Action").selectOption({ label: "5: Lockdown" });
  await form.getByRole("button", { name: "Log it", exact: true }).click();
  await expect(l.getByRole("listitem", { name: "Entry UW1" }).getByText("REDACTED")).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E3" }).getByText("By hand, for December")).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E3" }).getByText(/logged by infl-lead/)).toBeVisible();

  // The NPC's own page has its history, for staff, and the tool with it filled in.
  await l.goto(`/characters/${npc}/influence`);
  await expect(l.getByRole("listitem", { name: "Entry E3" })).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E2" })).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E1" })).toHaveCount(0);
  await expect(l.getByText("Elite: 2 spent: 2 logged by staff.")).toBeVisible();
  await l.getByRole("button", { name: "Log influence for Prince Vasquez" }).click();
  await expect(l.getByRole("dialog").getByLabel("Who")).toHaveValue("Prince Vasquez");
  await l.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();

  // The player sees Corvin's own action, and no one else's, nor the tool.
  await p.goto(`/characters/${corvin}`);
  await characterTab(p, "Influence");
  const own = p.getByRole("listitem", { name: "Entry E1" });
  await expect(own.getByText("Elite · 4: Smooth Over")).toBeVisible();
  await expect(own.getByText("To bury the inspector's report")).toBeVisible();
  await expect(p.getByRole("listitem", { name: /Entry (E2|E3|UW1)/ })).toHaveCount(0);
  await expect(p.getByText("Elite: 4 of 3 spent: 4 logged by staff.")).toBeVisible();
  await expect(p.getByRole("button", { name: /Log influence/ })).toHaveCount(0);
  await p.getByLabel("Findable now (last 90 days)").check();
  await expect(own).toBeVisible();
  await p.getByLabel("Type").selectOption({ label: "Underworld" });
  await expect(p.getByText("No influence actions match these filters.")).toBeVisible();
  await p.screenshot(shots("influence-history"));
});

test("influence spent at a game goes in the troupe's influence log, and comes off the next downtime", async ({ browser }) => {
  // A whole character creation, a home troupe, then a game and a downtime.
  test.slow();
  const custodian = await person(browser, "game-infl-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "game-infl-lead");
  const player = await person(browser, "game-infl-player");
  const troupeName = `Court of Whispers ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  await backstoryOptional(custodian.page, troupeName);
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };

  // Iris, built for the troupe with Elite 3, takes a News Media specialisation and makes it her home.
  const p = player.page;
  await p.reload();
  await p.getByLabel("Name").fill("Iris");
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
  await tap("Influences: The Elite 3", "Herd 2", "Generation 1");
  await next("Disciplines");
  await tap("Celerity 2", "Potence 1", "Presence 1");
  await next("Merits & flaws");
  await next("Review");
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  const iris = new URL(p.url()).pathname.split("/")[2]!;
  const special = await p.request.put(`/api/characters/${iris}/traits`, {
    headers,
    data: { category: "influence_elite_specializations", name: "News Media", rating: 1 },
  });
  expect(special.status(), await special.text()).toBe(200);
  await characterTab(p, "Troupes");
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(/Waiting for .* storytellers/)).toBeVisible();
  const queue = await l.request.get(`/api/troupes/${troupeId}/approvals`, { headers });
  for (const request of await queue.json()) {
    const approved = await l.request.post(`/api/approvals/${request.id}/approve`, { headers, data: {} });
    expect(approved.status(), await approved.text()).toBe(200);
  }

  // At the game: spending Elite always asks what it was for, offering only the actions Iris can reach.
  await p.goto(`/play/characters/${iris}`);
  const elite = p.getByRole("listitem").filter({ hasText: "Influences: The Elite" });
  await expect(elite.getByText("Backgrounds · 3 of 3 left")).toBeVisible();
  await expect(elite.getByRole("button", { name: /^Restore/ })).toHaveCount(0);
  await p.getByRole("button", { name: "Use Influences: The Elite" }).click();
  const sheet = p.getByRole("dialog", { name: "Spend Elite influence" });
  await expect(sheet.getByLabel("Action").getByRole("option", { name: "5: No Party Crashers" })).toHaveCount(0);
  await sheet.getByLabel("Specialisation").selectOption("News Media");
  await expect(sheet.getByText("Your News Media specialisation counts your Elite as 4 for this.")).toHaveCount(0);
  await sheet.getByLabel("Action").selectOption({ label: "4: Smooth Over" });
  await expect(sheet.getByText("Your News Media specialisation counts your Elite as 4 for this.")).toBeVisible();
  await sheet.getByLabel("Action").selectOption({ label: "2: Gossip and Insider Trading" });
  await sheet.getByLabel("Purpose").fill("To hear what is said about the mayor");
  await p.screenshot(shots("play-influence"));
  await sheet.getByRole("button", { name: "Spend", exact: true }).click();
  await expect(p.getByText("Elite: 2: Gossip and Insider Trading (News Media), To hear what is said about the mayor")).toBeVisible();
  await expect(elite.getByText("Backgrounds · 2 of 3 left")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // A loud room: Skip details spends it all the same.
  await p.getByRole("button", { name: "Use Influences: The Elite" }).click();
  await sheet.getByRole("button", { name: "Skip details" }).click();
  await expect(p.getByText("Elite: details to come")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // One spent by mistake, and undone.
  await p.getByRole("button", { name: "Use Influences: The Elite" }).click();
  await sheet.getByRole("button", { name: "Skip details" }).click();
  await expect(elite.getByText("Backgrounds · 0 of 3 left")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await (await undoInHeader(p, "Elite: details to come")).click();
  await expect(p.getByText("Undid: Influences: The Elite 1 → 0")).toBeVisible();
  await expect(elite.getByText("Backgrounds · 1 of 3 left")).toBeVisible();

  // The troupe's influence log has the two spends, one needing details, and not the one undone.
  await l.goto(`/troupes/${troupeId}/influence`);
  const e1 = l.getByRole("listitem", { name: "Entry E1" });
  await expect(e1.getByText("To hear what is said about the mayor")).toBeVisible();
  await expect(e1.getByText("At a game")).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E2" }).getByText("Needs details")).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E3" })).toHaveCount(0);

  // Iris adds the details from the game's log, while the game goes on.
  await p.getByRole("button", { name: "Add details to E2" }).click();
  const later = p.getByRole("dialog", { name: "Details of E2" });
  await later.getByLabel("Action").selectOption({ label: "1: A Friend in Need" });
  await later.getByLabel("Purpose").fill("To get a favour from the mayor's aide");
  await later.getByRole("button", { name: "Save details" }).click();
  await expect(p.getByText("Elite: 1: A Friend in Need, To get a favour from the mayor's aide")).toBeVisible();
  await l.reload();
  await expect(l.getByRole("listitem", { name: "Entry E2" }).getByText("To get a favour from the mayor's aide")).toBeVisible();

  // One pool a month: the next downtime's Elite allowance is two lower, for the two spent at the game.
  const now = Date.now();
  const made = await l.request.post(`/api/troupes/${troupeId}/cycles`, {
    headers,
    data: { name: "After the game", closes_at: new Date(now + 7 * 86400e3).toISOString(), grace_ends_at: new Date(now + 9 * 86400e3).toISOString() },
  });
  expect(made.status(), await made.text()).toBe(201);
  const cycleId = (await made.json()).id;
  const opened = await l.request.post(`/api/cycles/${cycleId}/open`, { headers });
  expect(opened.status(), await opened.text()).toBe(200);
  await l.goto(`/cycles/${cycleId}/participants`);
  await l.getByRole("button", { name: /^More for / }).click();
  await expect(l.getByText(/1 influence elite/)).toBeVisible();
  await expect(l.getByText(/^-1 influence_elite: Spent at the \d+ \w+ game$/)).toHaveCount(2);
  await l.screenshot(shots("cycle-influence-owed"));
});

test("Gossip is filled from the influence log, and a discovery block hides an entry from it", async ({ browser }) => {
  // A whole character creation, then a downtime answered from the log.
  test.slow();
  const custodian = await person(browser, "gossip-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "gossip-lead");
  const player = await person(browser, "gossip-player");
  const troupeName = `Court of Rumours ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  await backstoryOptional(custodian.page, troupeName);
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };

  // Agnes is built for the troupe, then takes Elite 3 with News Media, and joins it.
  const p = player.page;
  await p.reload();
  await p.getByLabel("Name").fill("Agnes");
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
  const agnes = new URL(p.url()).pathname.split("/")[2]!;
  for (const [category, name, rating] of [
    ["backgrounds", "Influences: The Elite", 3],
    ["influence_elite_specializations", "News Media", 1],
  ] as const) {
    const bought = await p.request.put(`/api/characters/${agnes}/traits`, { headers, data: { category, name, rating } });
    expect(bought.status(), await bought.text()).toBe(200);
  }
  const asked = await p.request.post(`/api/characters/${agnes}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBe(201);
  const approved = await l.request.post(`/api/approvals/${(await asked.json()).id}/approve`, { headers, data: {} });
  expect(approved.status(), await approved.text()).toBe(200);

  // A cycle, and the troupe's log: three Elite actions by someone else in News Media, one
  // of them blocked once and one too long ago, and one of Agnes's own.
  const day = 24 * 60 * 60 * 1000;
  const closes = new Date(Date.now() + 7 * day);
  const made = await l.request.post(`/api/troupes/${troupeId}/cycles`, {
    headers,
    data: { name: "Winter", closes_at: closes.toISOString(), grace_ends_at: new Date(closes.getTime() + 7 * day).toISOString() },
  });
  expect(made.status(), await made.text()).toBe(201);
  const cycleId = (await made.json()).id;
  expect((await l.request.post(`/api/cycles/${cycleId}/open`, { headers })).status()).toBe(200);
  for (const [who, action_key, purpose, daysBeforeClose, blocks] of [
    ["REDACTED", "smooth_over", "To bury the mayor's scandal", 17, 0],
    ["REDACTED", "no_party_crashers", "To keep the press out of the gala", 100, 0],
    ["agnes", "a_friend_in_need", "To call in a favour from the editor", 12, 0],
    ["REDACTED", "bureaucratic_errors", "To lose the dock permits", 27, 1],
  ] as const) {
    const data = {
      type: "elite",
      happened_at: new Date(closes.getTime() - daysBeforeClose * day).toISOString(),
      ...(who === "agnes" ? { character_id: agnes } : { name: who }),
      specialization: "News Media",
      action_key,
      purpose,
      blocks,
    };
    const logged = await l.request.post(`/api/troupes/${troupeId}/influence-log`, { headers, data });
    expect(logged.status(), await logged.text()).toBe(201);
  }

  // Agnes spends two actions on Gossip, and one hiding her own favour from the editor.
  await p.goto(`/characters/${agnes}/downtime`);
  const elite = p.locator("section").filter({ has: p.getByRole("heading", { name: "Elite influence action" }) });
  const answer = async (i: number, text: string, action: string) => {
    await elite.getByRole("button", { name: /Add an action/ }).click();
    await elite.getByLabel("Elite influence action").nth(i).fill(text);
    await elite.getByLabel("Specialisation").nth(i).selectOption("News Media");
    await elite.getByLabel("Action", { exact: true }).nth(i).selectOption({ label: action });
  };
  await answer(0, "Ask the newsroom what is stirring.", "2: Gossip and Insider Trading");
  await expect(elite.getByText("Covers all your specialisations; more actions find better-hidden things.")).toBeVisible();
  await answer(1, "Ask again at the Herald.", "2: Gossip and Insider Trading");
  await answer(2, "Bury the favour I called in from the editor.", "Discovery block");
  await elite.getByLabel("Whose action to hide").selectOption({ label: "One of mine" });
  // Only her own actions to pick from, by their ids.
  const own = elite.getByLabel("Your action").locator("option", { hasText: "To call in a favour from the editor" });
  await expect(own).toHaveText(/^E3 · /);
  await expect(elite.getByLabel("Your action").locator("option")).toHaveCount(2);
  await elite.getByLabel("Your action").selectOption((await own.getAttribute("value"))!);
  await p.getByRole("button", { name: "Submit downtime" }).click();
  await expect(p.getByText("Submitted", { exact: true })).toBeVisible();

  // The lead fills the first Gossip answer from the log: the result goes on the last,
  // strength 2, so the once-blocked entry shows, and never Agnes's own or who took them.
  await l.goto(`/cycles/${cycleId}/responses`);
  const responses = l.getByRole("textbox", { name: "Response to Agnes" });
  await l.getByRole("button", { name: "Fill from the log" }).first().click();
  await expect(responses.nth(0)).toHaveValue("Combined with your other Gossip and Insider Trading actions: strength 2, results below.");
  const result = l.getByRole("textbox", { name: "Combined response: Ask again at the Herald." });
  await expect(result).toHaveValue(/^Gossip and Insider Trading, strength 2, in News Media, since .*:\n- .*, News Media, 3: Bureaucratic Errors, To lose the dock permits \(E4\)\n- .*, News Media, 4: Smooth Over, To bury the mayor's scandal \(E1\)$/);
  await l.screenshot(shots("gossip"));
  await l.getByRole("button", { name: "Save response" }).first().click();
  await expect(responses.nth(1)).toHaveValue(/To bury the mayor's scandal \(E1\)$/);

  // The block, on the entry Agnes picked.
  await expect(l.getByLabel("Entry to block").locator("option:checked")).toHaveText(/^E3 · .* · Agnes · Elite, News Media · 1: A Friend in Need/);
  await l.getByRole("button", { name: "Accept the block" }).click();
  await expect(l.getByText("Blocked E3 (now 1).")).toBeVisible();
  await expect(responses.nth(2)).toHaveValue("Blocked (now 1).");

  // The log shows where the block came from.
  await l.goto(`/troupes/${troupeId}/influence`);
  const e3 = l.getByRole("listitem", { name: "Entry E3" });
  await expect(e3.getByText("1 block")).toBeVisible();
  await expect(e3.getByText(/Blocked by Agnes in Winter, accepted by gossip-lead/)).toBeVisible();

  // A longer lookback finds the action from 100 days back.
  await l.goto(`/troupes/${troupeId}/rules/actions`);
  await expect(l.getByText("90 days", { exact: true })).toBeVisible();
  await l.getByRole("button", { name: "Change how far lookups look back" }).click();
  await l.getByLabel("Days to look back").fill("120");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("120 days", { exact: true })).toBeVisible();
  await l.goto(`/cycles/${cycleId}/responses`);
  await l.getByRole("button", { name: "Fill from the log" }).first().click();
  await expect(l.getByRole("textbox", { name: "Combined response: Ask again at the Herald." })).toHaveValue(/To keep the press out of the gala \(E2\)/);
});

test("a storyteller resolves an attack, its target's Defend taken off, and the target's influence counts lower", async ({ browser }) => {
  const custodian = await person(browser, "attack-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "attack-lead");
  const troupeName = `Court of Knives ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Two NPCs, made straight through the API: Isolde with Elite 4, Vasquez with Elite 3.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const npcs: Record<string, string> = {};
  for (const [name, elite] of [
    ["Isolde", 4],
    ["Vasquez", 3],
  ] as const) {
    const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(made.status(), await made.text()).toBe(201);
    npcs[name] = (await made.json()).id;
    const rated = await p.request.put(`/api/characters/${npcs[name]}/npc/ratings`, {
      headers,
      data: { category: "backgrounds", name: "Influences: The Elite", rating: elite, detail: "" },
    });
    expect(rated.status(), await rated.text()).toBe(200);
  }
  // Vasquez defended a minute ago, before the attack.
  const defended = await p.request.post(`/api/troupes/${troupeId}/influence-log`, {
    headers,
    data: { type: "elite", happened_at: new Date(Date.now() - 60_000).toISOString(), character_id: npcs.Vasquez, action_key: "defend" },
  });
  expect(defended.status(), await defended.text()).toBe(201);

  // The lead logs Isolde's attack on Vasquez's Elite, 4 actions: 2 levels.
  await p.goto(`/troupes/${troupeId}/influence`);
  await p.getByRole("button", { name: "Log influence" }).click();
  const form = p.getByRole("form", { name: "Log influence" });
  await form.getByLabel("Who", { exact: true }).fill("Isolde");
  await form.getByRole("option", { name: "Isolde NPC" }).click();
  await form.getByLabel("Action", { exact: true }).selectOption({ label: "Attack" });
  await form.getByLabel("Attacking").selectOption({ label: "Vasquez (NPC)" });
  await form.getByLabel("Times taken").fill("4");
  await form.getByRole("button", { name: "Log it" }).click();
  const attack = p.getByRole("listitem", { name: "Entry E2" });
  await expect(attack.getByText("Attack → Vasquez's Elite")).toBeVisible();

  // Resolving it shows the cost and the Defend taken off.
  await attack.getByRole("button", { name: "Resolve" }).click();
  const dialog = p.getByRole("dialog");
  await expect(dialog.getByText("An attack on Vasquez's Elite, at 3 now.")).toBeVisible();
  await expect(dialog.getByText("2 levels at 2 actions each: 4 actions. E2 spent 4.")).toBeVisible();
  await expect(dialog.getByLabel("Defends")).toContainText("Vasquez's Defends (E1) take 1 level off. Vasquez loses 1 level and as many actions");
  await p.screenshot(shots("influence-resolve"));
  await dialog.getByRole("button", { name: "Record the attack" }).click();
  await expect(attack.getByText("Elite 1 lower")).toBeVisible();
  await p.getByRole("navigation", { name: "Influence log" }).getByRole("link", { name: "Effects and blocks" }).click();
  await expect(p.getByRole("list", { name: "Effects and blocks" }).getByText("Vasquez: Elite 1 lower (1 defended)")).toBeVisible();

  // Vasquez's sheet shows it, and the Play View's Elite counter starts lower.
  await p.goto(`/characters/${npcs.Vasquez}/sheet`);
  await expect(p.getByRole("heading", { name: "Influence changed" })).toBeVisible();
  await expect(p.getByText(/\(attacked\), until .*, or 2 more games if that is later/)).toBeVisible();
  await p.goto(`/play/characters/${npcs.Vasquez}`);
  const elite = p.getByRole("listitem").filter({ hasText: "Influences: The Elite" });
  await expect(elite.getByText("2 of 2 left", { exact: false })).toBeVisible();

  // Taken back, the counter is whole again.
  await p.goto(`/troupes/${troupeId}/influence/effects`);
  p.once("dialog", (d) => void d.accept());
  await p.getByRole("list", { name: "Effects and blocks" }).getByRole("button", { name: "Take back" }).click();
  await expect(p.getByText("Nothing holding now.")).toBeVisible();
  await p.goto(`/play/characters/${npcs.Vasquez}`);
  await expect(p.getByRole("listitem").filter({ hasText: "Influences: The Elite" }).getByText("3 of 3 left", { exact: false })).toBeVisible();
});
