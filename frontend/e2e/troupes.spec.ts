import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, backstoryOptional, characterTab } from "./support";

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
  await l.getByRole("link", { name: "Customize", exact: true }).click();
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
  await expect(l.getByText("replaced here")).toBeVisible();
  await expect(l.getByText("4 downtime actions")).toBeVisible();
  await l.screenshot(shots("actions"));

  // A character built for the troupe has that budget in the wizard.
  const p = player.page;
  await p.reload();
  await p.getByLabel("Name").fill("Mara");
  await p.getByLabel("Build for").selectOption({ label: troupeName });
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

  // The chronicle began before Horatio: the lead sets the floor and ceiling by hand, on About.
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
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
  await p.getByLabel("Build for").selectOption({ label: troupeName });
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
  const printTab = p.context().waitForEvent("page");
  await p.getByRole("button", { name: "Print all 2" }).click();
  const printed = await printTab;
  await expect(printed.getByText("2 sheets", { exact: true })).toBeVisible();
  await printed.close();
});

test("someone asks for a troupe of their own, and the custodian approves it", async ({ browser }) => {
  const custodian = await person(browser, "requests-custodian");
  makeCustodian(custodian.email);
  const asker = await person(browser, "requests-asker");
  const troupeName = `Court of Cinders ${run}`;

  const a = asker.page;
  await a.getByRole("link", { name: "Troupes" }).click();
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
  await expect(a.getByText("Lead Storyteller").first()).toBeVisible();
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
  await p.getByRole("button", { name: "Visit" }).click();
  await expect(p.getByRole("listitem").filter({ hasText: troupeName })).toBeVisible();
  // Home troupe comes first, then the visiting troupes, each with what it means.
  await expect(p.locator("main section h2")).toHaveText(["Home troupe", "Visiting troupes"]);
  const card = (title: string) => p.locator("main section").filter({ has: p.getByRole("heading", { name: title }) });
  await expect(card("Home troupe").getByText("The one troupe that holds this character's sheet.")).toBeVisible();
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
  await lead.page.getByRole("button", { name: "Save" }).click();
  await expect(lead.page.getByText(`@${player.handle} · Narrator`)).toBeVisible();

  // Now on the staff, they are greyed out with their role.
  await lead.page.getByLabel("Person").click();
  const added = people.getByRole("option", { name: `@${player.handle}` });
  await expect(added).toHaveAttribute("aria-disabled", "true");
  await expect(added).toContainText("Narrator");
  // So is the lead.
  await lead.page.getByLabel("Person").fill(lead.handle);
  await expect(people.getByRole("option", { name: `@${lead.handle}` })).toHaveAttribute("aria-disabled", "true");
  await expect(people.getByRole("option", { name: `@${lead.handle}` })).toContainText("Lead Storyteller");
  await lead.page.keyboard.press("Escape");

  // Their role is changed in the staff list.
  await lead.page.getByLabel("Role for staff-player").selectOption("assistant_storyteller");
  await expect(lead.page.getByText(`@${player.handle} · Assistant Storyteller`)).toBeVisible();
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

test("a troupe's Profile tab switches it public at once, About sets its XP range, and Waiting on you leads to the work", async ({ browser }) => {
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

  // About: the lead sets the XP floor and ceiling by hand, with Award XP beside them.
  await l.getByRole("link", { name: "About", exact: true }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}$`));
  // The Profile tab's form can linger a moment after the URL changes, with the description in it.
  await expect(l.getByRole("textbox", { name: "Description" })).toHaveCount(0);
  await expect(l.getByText("A court that meets where the roads cross.")).toBeVisible();
  await expect(l.locator("main").getByRole("link", { name: "Award XP", exact: true })).toBeVisible();
  await l.getByRole("button", { name: "Set by hand" }).click();
  await l.getByLabel("Floor", { exact: true }).fill("60");
  await l.getByLabel("Ceiling", { exact: true }).fill("75");
  await l.getByLabel("Why", { exact: true }).fill("Chronicle began in 2021");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("(30 starting + 30 set by hand)")).toBeVisible();
  await expect(l.getByText("(30 starting + 45 set by hand)")).toBeVisible();
  // Starting points keeps a copy to read, which leads back to About.
  await l.goto(`/troupes/${troupeId}/rules/starting`);
  await expect(l.getByText("60 XP", { exact: true })).toBeVisible();
  await expect(l.getByRole("button", { name: "Set by hand" })).toHaveCount(0);
  await l.getByRole("link", { name: "Set them on About" }).click();
  await expect(waiting).toBeVisible();

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

  // The player sees About without the box, and the XP range only to read.
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByRole("heading", { name: "XP floor and ceiling" })).toBeVisible();
  await expect(p.getByText("60 XP", { exact: true })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Waiting on you" })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Set by hand" })).toHaveCount(0);
});
