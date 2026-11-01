import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, backstoryOptional, characterTab } from "./support";

/** The Who's Who, and what a player says about their character and themselves. */

closeContextsAfterEach();

test("why a character left: a player retires one Off-field and it is no longer with us; one unlisted is nowhere on the Who's Who", async ({ browser }) => {
  const custodian = await person(browser, "departed-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "departed-lead");
  const ana = await person(browser, "departed-ana");
  const bea = await person(browser, "departed-bea");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Empty Chairs ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;
  const send = async (page: Page, method: "POST" | "PUT" | "GET", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  // A Camarilla Toreador, built through the API and accepted home.
  const build = async (page: Page, name: string): Promise<string> => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Toreador", rating: null });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
      disciplines: [["Auspex", 2], ["Celerity", 1], ["Presence", 1]],
    };
    for (const [category, chosen] of Object.entries(picks))
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: chosen.map(([name, rating]) => ({ name, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`, {});
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});
    return id;
  };
  // Celeste is the Harpy; Hortense is Ana's too, and Bastien is Bea's.
  const celeste = await build(ana.page, "Celeste");
  const hortense = await build(ana.page, "Hortense");
  await build(bea.page, "Bastien");
  await send(lead.page, "PUT", `/api/troupes/${troupeId}/characters/${celeste}/titles`, { titles: ["Harpy"] });

  // Ana retires Celeste, Off-field, from the ⋯ menu. Listed is the default.
  const p = ana.page;
  const retire = async (id: string, name: string, reason: RegExp, listed: boolean, note = "") => {
    await p.goto(`/characters/${id}`);
    await p.getByRole("button", { name: `More for ${name}` }).click();
    await p.getByRole("menuitem", { name: "Retire…" }).click();
    const dialog = p.getByRole("dialog", { name: `Retire ${name}` });
    await dialog.getByRole("radio", { name: reason }).check();
    if (note) await dialog.getByLabel("Note (optional)").fill(note);
    const listing = dialog.getByRole("checkbox", { name: /under “No longer with us”/ });
    if (listed) await expect(listing).toBeChecked();
    else await expect(listing).not.toBeChecked();
    return dialog;
  };
  const dialog = await retire(celeste, "Celeste", /^Off-field/, true, "Gone to Chicago.");
  await p.screenshot(shots("retire"));
  await dialog.getByRole("button", { name: "Retire Celeste" }).click();
  await expect(p.getByText("Why Celeste left: Off-field.")).toBeVisible();
  await expect(p.getByText("Listed under “No longer with us” on the Who's Who.")).toBeVisible();
  await characterTab(p, "Log");
  await expect(p.getByText("retired Celeste: Off-field, listed under No longer with us. Gone to Chicago.")).toBeVisible();
  // Hortense is Inactive, unlisted by default, and Ana leaves it so.
  await (await retire(hortense, "Hortense", /^Inactive/, false)).getByRole("button", { name: "Retire Hortense" }).click();
  await expect(p.getByText("Why Hortense left: Inactive.")).toBeVisible();
  await expect(p.getByText("Not on the Who's Who.")).toBeVisible();

  // On Bea's Who's Who, Celeste is no longer with us, with why, and in no other view.
  const b = bea.page;
  await b.goto(`/troupes/${troupeId}/whos-who`);
  const section = (name: string) => b.getByRole("region", { name, exact: true });
  const gone = section("No longer with us").getByRole("article", { name: "Celeste" });
  await expect(gone.getByText("Off-field")).toBeVisible();
  await expect(gone.getByRole("link", { name: "departed-ana" })).toBeVisible();
  await expect(b.getByRole("article", { name: "Celeste" })).toHaveCount(1);
  await expect(section("Court")).toHaveCount(0);
  await expect(section("Toreador").getByRole("article", { name: "Bastien" })).toBeVisible();
  // Hortense, unlisted, is nowhere.
  await expect(b.getByRole("article", { name: "Hortense" })).toHaveCount(0);
  await b.screenshot(shots("whos-who-departed"));
});

test("represented by: a Ravnos's player says the Brujah speak for them at court, and seating the Ravnos gives them their own section", async ({ browser }) => {
  const custodian = await person(browser, "repby-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "repby-lead");
  const bruno = await person(browser, "repby-bruno");
  const ravi = await person(browser, "repby-ravi");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Seats ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;
  const send = async (page: Page, method: "POST" | "PUT" | "GET", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  // A Camarilla character of `clan`, built through the API and accepted home.
  const build = async (page: Page, name: string, clan: string, inClan: [string, number][]): Promise<string> => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: clan, rating: null });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
      disciplines: inClan,
    };
    for (const [category, chosen] of Object.entries(picks))
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: chosen.map(([name, rating]) => ({ name, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`, {});
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});
    return id;
  };
  // The Brujah hold a Primogen, so they have a seat; the Ravnos don't.
  const roth = await build(bruno.page, "Rothgar", "Brujah", [["Celerity", 2], ["Potence", 1], ["Presence", 1]]);
  await build(ravi.page, "Ravindra", "Ravnos", [["Chimerstry", 2], ["Animalism", 1], ["Fortitude", 1]]);
  await send(lead.page, "PUT", `/api/troupes/${troupeId}/characters/${roth}/titles`, { titles: ["Primogen"] });

  // Ravindra's player says the Brujah speak for them.
  const p = ravi.page;
  await p.goto(`/troupes/${troupeId}/whos-who`);
  const section = (name: string) => p.getByRole("region", { name, exact: true });
  const card = section("Other").getByRole("article", { name: "Ravindra" });
  await expect(card.getByText("Represented by: nobody yet")).toBeVisible();
  await card.getByRole("button", { name: "Change who represents Ravindra" }).click();
  await card.getByLabel("Who represents Ravindra").selectOption("Brujah");
  await card.getByRole("button", { name: "Save" }).click();
  await expect(card.getByText("Represented by: Brujah")).toBeVisible();
  await p.screenshot(shots("represented-by"));
  // Only their own: Rothgar's Brujah have a seat, and nothing to choose.
  await expect(section("Brujah").getByRole("button", { name: /Change who represents/ })).toHaveCount(0);

  // Staff see it on the Characters tab.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/characters`);
  await expect(l.getByRole("listitem").filter({ hasText: "Ravindra" }).getByText("Represented by: Brujah")).toBeVisible();

  // Seating the Ravnos moves Ravindra into their own section.
  await l.goto(`/troupes/${troupeId}/titles`);
  const seats = l.getByRole("group", { name: "Clans with a seat at court" });
  await expect(seats.getByLabel("Brujah", { exact: true })).toBeChecked();
  await expect(seats.getByLabel("Ravnos", { exact: true })).not.toBeChecked();
  // It saves, then shows ticked.
  await seats.getByLabel("Ravnos", { exact: true }).click();
  await expect(l.getByText("You chose these clans.")).toBeVisible();
  await expect(seats.getByLabel("Ravnos", { exact: true })).toBeChecked();
  await p.reload();
  await expect(section("Ravnos").getByRole("article", { name: "Ravindra" })).toBeVisible();
  await expect(section("Other")).toHaveCount(0);
});

test("the Who's Who: a player sees the court in rank order, their clan and Other, finds a character by its player, and prints it; others are refused", async ({ browser }) => {
  const custodian = await person(browser, "whoswho-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "whoswho-lead");
  const ana = await person(browser, "whoswho-ana");
  const bea = await person(browser, "whoswho-bea");
  const cy = await person(browser, "whoswho-cy");
  const outsider = await person(browser, "whoswho-outsider");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Hall of Names ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;
  const send = async (page: Page, method: "POST" | "PUT" | "GET", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  // A Camarilla character of `clan`, built through the API and accepted home.
  const build = async (page: Page, name: string, clan: string, inClan: [string, number][]): Promise<string> => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: clan, rating: null });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
      disciplines: inClan,
    };
    for (const [category, chosen] of Object.entries(picks))
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: chosen.map(([name, rating]) => ({ name, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`, {});
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});
    return id;
  };
  const brujah: [string, number][] = [["Celerity", 2], ["Potence", 1], ["Presence", 1]];
  // Varga is the Prince and the Ventrue Primogen, Roth the Brujah Primogen, and the
  // Gangrel, with no Primogen, have no seat: Wren is under Other.
  const varga = await build(ana.page, "Varga", "Ventrue", [["Dominate", 2], ["Fortitude", 1], ["Presence", 1]]);
  const roth = await build(bea.page, "Roth", "Brujah", brujah);
  await build(cy.page, "Wren", "Gangrel", [["Animalism", 2], ["Fortitude", 1], ["Protean", 1]]);
  await send(lead.page, "PUT", `/api/troupes/${troupeId}/characters/${roth}/titles`, { titles: ["Primogen"] });
  await send(lead.page, "PUT", `/api/troupes/${troupeId}/characters/${varga}/titles`, { titles: ["Primogen", "Prince"] });

  // Ana opens it from the troupe's page.
  const p = ana.page;
  await p.goto(`/troupes/${troupeId}`);
  await p.getByRole("link", { name: "Who's Who" }).click();
  const section = (name: string) => p.getByRole("region", { name, exact: true });
  const named = (name: string) => section(name).getByRole("article").evaluateAll((cards) => cards.map((c) => c.getAttribute("aria-label")));
  await expect(section("Court").getByRole("article")).toHaveCount(2);
  // The court in rank order, the Prince first with both titles.
  expect(await named("Court")).toEqual(["Varga", "Roth"]);
  await expect(section("Court").getByRole("article", { name: "Varga" }).getByText("Prince")).toBeVisible();
  expect(await named("Ventrue")).toEqual(["Varga"]);
  expect(await named("Brujah")).toEqual(["Roth"]);
  const wren = section("Other").getByRole("article", { name: "Wren" });
  await expect(wren.getByText("Represented by: nobody yet")).toBeVisible();
  await expect(wren.getByRole("link", { name: "whoswho-cy" })).toBeVisible();
  // The Camarilla bans a non-pillar clan's status, which others see.
  await expect(wren.getByText(/Lesser status ban: Not Embraced into a pillar clan/)).toBeVisible();
  await p.screenshot(shots("whos-who"));

  // Searching by a player's name finds their character, in each section it is in.
  await p.getByLabel("Search the Who's Who").fill("whoswho-bea");
  await expect(section("Brujah").getByRole("article", { name: "Roth" })).toBeVisible();
  await expect(p.getByRole("article", { name: "Varga" })).toHaveCount(0);
  await expect(p.getByRole("article", { name: "Wren" })).toHaveCount(0);
  await p.getByLabel("Search the Who's Who").fill("");
  await p.getByLabel("Clan", { exact: true }).selectOption("Gangrel");
  expect(await named("Other")).toEqual(["Wren"]);
  await expect(section("Court")).toHaveCount(0);

  // The print view prints every section.
  const printed = await p.context().newPage();
  await printed.goto(`/print/troupes/${troupeId}/whos-who`);
  for (const name of ["Court", "Brujah", "Ventrue", "Other"]) await expect(printed.getByRole("region", { name, exact: true })).toBeVisible();
  await expect(printed.getByRole("region", { name: "Other" }).getByText("Nobody yet")).toBeVisible();
  await printed.screenshot(shots("whos-who-print"));

  // From the Play View, another at the game links to their entry.
  await p.goto(`/play/characters/${varga}?tab=status`);
  const others = p.locator("section").filter({ has: p.getByRole("heading", { name: "Others at this game" }) });
  await others.getByRole("button", { name: /Roth/ }).click();
  await others.getByRole("link", { name: "Roth on the Who’s Who" }).click();
  await expect(p).toHaveURL(new RegExp(`/troupes/${troupeId}/whos-who#c-${roth}$`));
  await expect(section("Brujah").getByRole("article", { name: "Roth" })).toBeInViewport();

  // Someone with no character in the troupe sees no Who's Who, and the API refuses them.
  const o = outsider.page;
  await o.goto(`/troupes/${troupeId}`);
  await expect(o.getByRole("link", { name: "Profile", exact: true })).toBeVisible();
  await expect(o.getByRole("link", { name: "Who's Who" })).toHaveCount(0);
  const refused = await o.request.get(`/api/troupes/${troupeId}/whos-who`, { headers });
  expect(refused.status()).toBe(403);
});

test("lines and veils: a player adds them, staff see them, another player only once shared, and no one outside the troupe", async ({ browser }) => {
  const custodian = await person(browser, "lv-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "lv-lead");
  const ana = await person(browser, "lv-ana");
  const bea = await person(browser, "lv-bea");
  const outsider = await person(browser, "lv-outsider");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Veiled Court ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  const send = async (page: Page, method: "POST" | "PUT" | "GET", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  // Each has a character visiting the troupe.
  for (const [who, name] of [[ana, "Odile"], [bea, "Petra"]] as const) {
    const { id } = await send(who.page, "POST", "/api/characters", { splat: "vampire", name });
    await send(who.page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Toreador", rating: null });
    await send(who.page, "POST", `/api/characters/${id}/troupes`, { troupe_id: troupeId });
  }
  const anaId = (await send(ana.page, "GET", "/api/auth/me")).id;

  // Ana writes a line and a veil on her account, with sharing off as it starts.
  const a = ana.page;
  await a.goto("/account");
  await a.locator("main").getByRole("link", { name: "Lines and veils" }).click();
  await expect(a.getByText("A veil can happen in the story, but off-screen")).toBeVisible();
  await expect(a.getByLabel("Line 1", { exact: true })).toHaveAttribute("placeholder", "e.g. spiders");
  await a.getByLabel("Line 1", { exact: true }).fill("Spiders in the dark");
  await a.getByRole("button", { name: "Add a line" }).click();
  await a.getByLabel("Line 2", { exact: true }).fill("Drowning");
  await a.getByLabel("Veil 1", { exact: true }).fill("Needles");
  const share = a.getByRole("checkbox", { name: /Share my lines and veils with other players in my troupes/ });
  await expect(share).not.toBeChecked();
  await expect(a.getByText("Off: only the staff of the troupes you play in see them.")).toBeVisible();
  await a.getByRole("button", { name: "Save lines and veils" }).click();
  await expect(a.getByText("Lines and veils saved.")).toBeVisible();
  await a.screenshot(shots("lines-veils-account"));

  // The lead sees them on the Who's Who, the Characters tab and the troupe's list.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/whos-who`);
  const odile = l.getByRole("article", { name: "Odile" });
  await expect(odile.getByRole("definition").filter({ hasText: "Spiders in the dark, Drowning" })).toBeVisible();
  await expect(odile.getByRole("definition").filter({ hasText: "Needles" })).toBeVisible();
  await l.goto(`/troupes/${troupeId}/characters`);
  await expect(l.getByLabel("Lines and veils of lv-ana")).toContainText("Spiders in the dark");
  await l.goto(`/troupes/${troupeId}/players`);
  await l.getByRole("link", { name: "Lines and veils" }).click();
  await expect(l.getByRole("list", { name: "Lines" })).toContainText("Spiders in the dark");
  await expect(l.getByRole("list", { name: "Veils" })).toContainText("Needles");
  // Not shared, so the list doesn't say whose they are; the lead opens Ana for that.
  await expect(l.getByRole("list", { name: "Lines" }).getByRole("link")).toHaveCount(0);
  await l.screenshot(shots("lines-veils-troupe"));
  await l.getByRole("link", { name: /lv-ana/ }).click();
  await expect(l.getByLabel("Lines and veils of lv-ana")).toContainText("Needles");
  // Never printed.
  await l.goto(`/print/troupes/${troupeId}/whos-who`);
  await expect(l.getByRole("region", { name: "Toreador" })).toBeVisible();
  await expect(l.getByText("Spiders in the dark")).toHaveCount(0);

  // Bea, another player, doesn't see them until Ana shares them.
  const b = bea.page;
  await b.goto(`/troupes/${troupeId}/whos-who`);
  await expect(b.getByRole("article", { name: "Odile" })).toBeVisible();
  await expect(b.getByText("Spiders in the dark")).toHaveCount(0);
  expect((await send(b, "GET", `/api/players/${anaId}`)).lines_veils).toBeNull();
  expect((await b.request.get(`/api/troupes/${troupeId}/lines-veils`, { headers })).status()).toBe(403);

  await share.check();
  await expect(a.getByText("On: the other players in your troupes see them on the Who’s Who, as well as the staff.")).toBeVisible();
  await a.getByRole("button", { name: "Save lines and veils" }).click();
  await expect(a.getByText("Lines and veils saved.")).toBeVisible();
  await b.reload();
  await expect(b.getByRole("article", { name: "Odile" }).getByLabel("Lines and veils of lv-ana")).toContainText("Spiders in the dark");

  // Someone outside the troupe never sees them, and the API refuses them.
  const o = outsider.page;
  await o.goto(`/players/${anaId}`);
  await expect(o.getByRole("heading", { name: "lv-ana" })).toBeVisible();
  await expect(o.getByText("Spiders in the dark")).toHaveCount(0);
  expect((await send(o, "GET", `/api/players/${anaId}`)).lines_veils).toBeNull();
  expect((await o.request.get(`/api/troupes/${troupeId}/lines-veils`, { headers })).status()).toBe(403);
  expect((await o.request.get(`/api/troupes/${troupeId}/whos-who`, { headers })).status()).toBe(403);
});

test("pronouns: a player gives their own and their character's, the Who's Who shows both, and badges print only the character's once the troupe says", async ({ browser }) => {
  const custodian = await person(browser, "pronouns-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "pronouns-lead");
  const player = await person(browser, "pronouns-play");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Hall of Voices ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;
  const send = async (page: Page, method: "POST" | "PUT", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  // Ines, a Camarilla Toreador built through the API and accepted home.
  const p = player.page;
  const { id } = await send(p, "POST", "/api/characters", { splat: "vampire", name: "Ines" });
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Toreador", rating: null });
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
  const picks: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Auspex", 2], ["Celerity", 1], ["Presence", 1]],
  };
  for (const [category, chosen] of Object.entries(picks))
    await send(p, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: chosen.map(([name, rating]) => ({ name, rating })) });
  await send(p, "POST", `/api/characters/${id}/creation/complete`, {});
  const asked = await send(p, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});

  // The player's own, on their profile: free text, with the usual ones suggested.
  await p.goto("/account");
  await p.getByLabel("Pronouns").fill("they/them");
  await p.getByRole("button", { name: "Save profile" }).click();
  await expect(p.getByText("Saved.")).toBeVisible();
  await p.getByRole("link", { name: "See your profile" }).click();
  await expect(p.getByRole("heading", { name: "pronouns-play (they/them)" })).toBeVisible();

  // Ines's, from the ⋯ menu on her page, beside her name once saved.
  await p.goto(`/characters/${id}`);
  await p.getByRole("button", { name: "More for Ines" }).click();
  await p.getByRole("menuitem", { name: "Pronouns…" }).click();
  await p.getByLabel("Pronouns").fill("she/her");
  await p.getByRole("button", { name: "Save pronouns" }).click();
  await expect(p.getByRole("heading", { name: "Ines (she/her)" })).toBeVisible();

  // The Who's Who shows both: hers beside her name, theirs beside theirs.
  await p.goto(`/troupes/${troupeId}/whos-who`);
  const ines = p.getByRole("article", { name: "Ines" }).first();
  await expect(ines.getByText("(she/her)")).toBeVisible();
  await expect(ines.getByText("(they/them)")).toBeVisible();
  await p.screenshot(shots("whos-who-pronouns"));

  // Badges print no pronouns until the troupe says, and then only the character's.
  const l = lead.page;
  await l.goto(`/print/troupes/${troupeId}/badges?characters=${id}`);
  const badge = l.getByRole("article", { name: "Badge for Ines" });
  await expect(badge.getByText("Neonate", { exact: false })).toBeVisible();
  await expect(badge.getByText("she/her")).toHaveCount(0);
  await l.goto(`/troupes/${troupeId}/settings`);
  const setting = l.locator("section").filter({ has: l.getByRole("heading", { name: "Badges", exact: true }) });
  await expect(setting.getByLabel(/^Print character pronouns/)).not.toBeChecked();
  await setting.getByLabel(/^Print character pronouns/).click();
  await expect(setting.getByLabel(/^Print character pronouns/)).toBeChecked();
  await l.goto(`/print/troupes/${troupeId}/badges?characters=${id}`);
  await expect(badge.getByText("she/her", { exact: true })).toBeVisible();
  await expect(badge.getByText(/they\/them/)).toHaveCount(0);
});
