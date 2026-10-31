import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, builtVampire, ATTRIBUTES_AND_FOCUSES, backstoryOptional } from "./support";

/** A character's page and sheet, and what a player asks staff for from it. */

closeContextsAfterEach();

test("a character in no troupe can be deleted from the vault", async ({ browser }) => {
  const { page } = await person(browser, "deleter");
  await page.getByLabel("Name").fill("Short-lived");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  // Delete waits behind the ⋯ menu beside Play, and asks first.
  await page.getByRole("button", { name: "More for Short-lived" }).click();
  await page.getByRole("menuitem", { name: "Delete…" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete Short-lived for good" }).click();

  await expect(page.getByRole("heading", { name: "Your characters" })).toBeVisible();
  await expect(page.getByText("No characters yet.")).toBeVisible();
});

test("merits and flaws on the sheet: Tainted Embrace caps fleeting status at 4 and says why, Slow Reactions lowers initiative, and Ardent Companion lists its Retainer (#314)", async ({ browser }) => {
  const custodian = await person(browser, "capflaw-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "capflaw-lead");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Ill Repute ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;

  // Hester, a Camarilla Nosferatu NPC: Physical 5, Mental 3, with Tainted Embrace,
  // Slow Reactions and Ardent Companion.
  const p = lead.page;
  const npc = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Hester", wizard: false } });
  expect(npc.status(), await npc.text()).toBe(201);
  const id = (await npc.json()).id;
  for (const [category, name, rating] of [
    ["clan", "Nosferatu", null],
    ["sect", "Camarilla", null],
    ["backgrounds", "Generation", 1],
    ["attributes", "Physical", 5],
    ["attributes", "Mental", 3],
    ["flaws", "Tainted Embrace", 2],
    ["flaws", "Slow Reactions", 3],
    ["merits", "Ardent Companion", 3],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${id}/npc/ratings`, { headers, data: { category, name, rating, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
  }

  // The Status tab: one fleeting status fewer, and why.
  await p.goto(`/characters/${id}/status`);
  const card = p.locator("section").filter({ has: p.getByRole("heading", { name: "Status", exact: true }) });
  await expect(card.getByRole("listitem", { name: "Acknowledged" })).toContainText("by the Camarilla");
  await expect(card.getByText("Fleeting: 0 of 4")).toBeVisible();
  await expect(card.getByText("Cap: Tainted Embrace: 1 less")).toBeVisible();
  await p.screenshot(shots("status-cap-flaw"));

  // The Sheet tab: Ardent Companion's ghouled animal, at the merit's 7, waiting for a name.
  await p.getByRole("link", { name: "Sheet", exact: true }).click();
  const companion = p.locator('[data-trait="Ardent Companion"]');
  await expect(companion.getByRole("list", { name: "Retainers" })).toContainText("Ghouled animal, not yet named · 7");

  // The Play View: initiative 5 lower, naming the flaw, and the cap at the game.
  await p.goto(`/play/characters/${id}`);
  await expect(p.getByRole("heading", { name: "Hester" })).toBeVisible();
  await p.getByRole("tab", { name: "Pools" }).click();
  const initiative = p.getByRole("listitem").filter({ hasText: /^Initiative/ });
  await expect(initiative).toContainText("Physical 5 − Slow Reactions 5");
  await expect(initiative.getByText("0", { exact: true })).toBeVisible();
  await p.screenshot(shots("pools-slow-reactions"));
  await p.getByRole("tab", { name: "Status" }).click();
  await expect(p.getByText("Fleeting: 0 of 4 (Cap: Tainted Embrace: 1 less)", { exact: false })).toBeVisible();
});

test("the sheet says what a trait does, under its name, and what a heading is, in an ⓘ", async ({ browser }) => {
  const { page: p } = await person(browser, "annotator");
  await p.getByLabel("Name").fill("Marginalia");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const id = new URL(p.url()).pathname.split("/")[2]!;
  const put = async (url: string, data: object) => {
    const response = await p.request.put(url, { headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBe(200);
  };
  await put(`/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  await put(`/api/characters/${id}/creation/categories/skills`, { picks: [{ name: "Brawl", rating: 2 }] });
  await put(`/api/characters/${id}/creation/categories/backgrounds`, { picks: [{ name: "Generation", rating: 1 }] });
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const fits = async (name: string) => {
    const box = (await p.getByText(name).boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(p.viewportSize()!.width);
  };

  // A skill opens to its description under the row, and closes again; the dots stay where they were.
  const brawl = part("Skills").getByRole("button", { name: "Brawl", exact: true });
  const about = p.getByText("Fighting with your body: fists, feet, grapples and claws.");
  await expect(brawl).toHaveAttribute("aria-expanded", "false");
  await expect(about).toHaveCount(0);
  await brawl.click();
  await expect(brawl).toHaveAttribute("aria-expanded", "true");
  await expect(about).toBeVisible();
  await expect(part("Skills").getByLabel("2 dots")).toBeVisible();
  await p.screenshot(shots("trait-info"));
  // A background with a book page gives it; several stay open together.
  const generation = part("Backgrounds").getByRole("button", { name: "Generation", exact: true });
  await generation.click();
  await expect(p.getByText("MET: VTM pp. 100-102")).toBeVisible();
  await expect(about).toBeVisible();
  await brawl.click();
  await expect(brawl).toHaveAttribute("aria-expanded", "false");
  await expect(about).toHaveCount(0);

  // A heading's ⓘ opens a small popover, closed by pressing it again, pressing outside, or Escape.
  const skills = part("Skills").getByRole("button", { name: "About Skills" });
  const words = p.getByText("What the character has learned to do");
  await skills.click();
  await expect(words).toBeVisible();
  await fits("What the character has learned to do");
  await skills.click();
  await expect(words).toHaveCount(0);
  await skills.click();
  await p.keyboard.press("Escape");
  await expect(words).toHaveCount(0);
  await expect(skills).toBeFocused();
  await skills.click();
  await expect(words).toBeVisible();
  await p.getByRole("heading", { name: "Marginalia" }).click();
  await expect(words).toHaveCount(0);

  // So does a choice in the page title, with the clan's in-clan disciplines.
  const clan = p.getByRole("button", { name: "About Brujah" });
  await clan.click();
  await expect(p.getByText("In-clan disciplines: Celerity, Potence, Presence.")).toBeVisible();
  await fits("In-clan disciplines: Celerity, Potence, Presence.");
  await p.screenshot(shots("clan-info"));
  await p.keyboard.press("Escape");
  await expect(p.getByText("In-clan disciplines: Celerity, Potence, Presence.")).toHaveCount(0);
});

test("a player renames their character once in three months, and the custodian any time", async ({ browser }) => {
  const custodian = await person(browser, "rename-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "rename-lead");
  const player = await person(browser, "rename-player");
  const troupeName = `Court of Lanterns ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Before any troupe has the character, renaming it is the player's own business.
  const p = player.page;
  await p.getByLabel("Name").fill("Agnes Moreau");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const rename = async (page: Page, from: string, to: string) => {
    await page.getByRole("button", { name: `More for ${from}` }).click();
    await page.getByRole("menuitem", { name: "Rename…" }).click();
    await page.getByLabel("New name").fill(to);
    await page.getByRole("button", { name: "Rename", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(to);
    await expect(page.getByRole("heading", { name: `Rename ${from}` })).toHaveCount(0);
  };
  await rename(p, "Agnes Moreau", "Agnes Bisset");
  await rename(p, "Agnes Bisset", "Agnes Moreau");

  // In a troupe, once every three months, and the troupe's storytellers are told.
  await p.locator("main").getByRole("link", { name: "Troupes", exact: true }).click();
  await p.getByLabel("Troupe to join").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Visit" }).click();
  await expect(p.getByRole("listitem").filter({ hasText: troupeName })).toBeVisible();
  await p.getByRole("button", { name: "More for Agnes Moreau" }).click();
  await p.getByRole("menuitem", { name: "Rename…" }).click();
  await p.getByLabel("New name").fill("Agnes Duval");
  await p.screenshot(shots("rename"));
  await p.getByRole("button", { name: "Rename", exact: true }).click();
  await expect(p.getByRole("heading", { level: 1 })).toHaveText("Agnes Duval");
  // The menu says when the next rename is allowed instead of offering one.
  await p.getByRole("button", { name: "More for Agnes Duval" }).click();
  await expect(p.getByText(/You can rename Agnes Duval again on/)).toBeVisible();
  await expect(p.getByRole("menuitem", { name: /^Rename/ })).toBeDisabled();
  await p.screenshot(shots("rename-wait"));
  await p.keyboard.press("Escape");

  await lead.page.reload();
  await lead.page.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(lead.page.getByText("Agnes Moreau is now called Agnes Duval")).toBeVisible();

  // The custodian can still rename it, which leaves the player's wait as it was.
  const c = custodian.page;
  await c.goto(new URL(p.url()).pathname.replace(/\/troupes$/, ""));
  await rename(c, "Agnes Duval", "Agnes Lemaire");
  await p.reload();
  await p.getByRole("button", { name: "More for Agnes Lemaire" }).click();
  await expect(p.getByText(/You can rename Agnes Lemaire again on/)).toBeVisible();
  await p.keyboard.press("Escape");
  await p.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(p.getByText("The custodian renamed Agnes Duval to Agnes Lemaire")).toBeVisible();
  await p.keyboard.press("Escape");

  // The character's history keeps the old names.
  await p.locator("main").getByRole("link", { name: "Log", exact: true }).click();
  await expect(p.getByText("rename-custodian renamed Agnes Duval to Agnes Lemaire (rename-player).")).toBeVisible();
  await expect(p.getByText("rename-player renamed Agnes Moreau to Agnes Duval.")).toBeVisible();
  await p.screenshot(shots("rename-log"));
});

test("the sheet points to the techniques and elder powers a character can take", async ({ browser }) => {
  const { page: p } = await person(browser, "finder-player");
  // A Pretender Elder (Generation 3) with Celerity 5: one elder power, and techniques at 20 XP.
  const id = await builtVampire(
    p,
    "Wren",
    "Brujah",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] },
    [["disciplines", "Celerity", 5]],
  );
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const disciplines = part("Disciplines");
  const chips = p.getByRole("navigation", { name: "Categories" });

  // One quiet line says what is open, and opens the Add panel there.
  await expect(disciplines.getByText(/Elder Disciplines? open to you\.$/)).toBeVisible();
  await p.screenshot(shots("open-to-you"));
  await disciplines.getByRole("button", { name: /^\d+ Elder Disciplines?$/ }).click();
  await expect(chips.getByRole("button", { name: /^Elder Disciplines/ })).toHaveAttribute("aria-pressed", "true");
  await expect(chips.getByRole("button", { name: /^Techniques/ })).toBeVisible();
  // Rituals need a ritual discipline, which a Brujah has not got.
  await expect(chips.getByRole("button", { name: /^Rituals/ })).toHaveCount(0);
  // What this character can take, by default: Celerity's elder powers, not Animalism's.
  await expect(p.getByLabel("Show")).toHaveValue("can");
  await expect(p.getByPlaceholder(/you can take…$/)).toBeVisible();
  await expect(p.getByRole("button", { name: "Celerity: Projectile" })).toBeVisible();
  await expect(p.getByRole("button", { name: /^Animalism: / })).toHaveCount(0);
  await expect(p.getByText(/^\d+ more you can't take:/)).toBeVisible();
  await p.getByLabel("Show").selectOption({ label: "Everything" });
  await expect(p.getByRole("button", { name: /^Animalism: / }).first()).toBeDisabled();
  await expect(p.getByText("An elder power needs all 5 dots of its discipline first.", { exact: false }).first()).toBeVisible();
  await p.screenshot(shots("elder-powers"));

  // A power's name finds it in whichever category it lives.
  await p.getByLabel("Search Elder Disciplines").fill("Fearful");
  await p.getByRole("button", { name: "Found in Techniques: Fearful Blow" }).click();
  await expect(chips.getByRole("button", { name: /^Techniques/ })).toHaveAttribute("aria-pressed", "true");
  await expect(p.getByRole("button", { name: /^Fearful Blow/ })).toBeDisabled();
  await expect(p.getByText("Fearful Blow needs Potence 2 and Presence 2.", { exact: false })).toBeVisible();

  // Dots in the cart open the technique straight away, before spending.
  await p.getByRole("button", { name: "Raise Potence" }).click();
  await p.getByRole("button", { name: "Raise Presence" }).click();
  await p.getByLabel("Show").selectOption({ label: "What this character can take" });
  await p.getByRole("button", { name: /^Fearful Blow/ }).click();
  // Pricing the cart is slow work for the server, the more so with the dry runs
  // for each dot still going: wait for the one that prices all three lines.
  const priced = p.waitForResponse((r) => r.url().endsWith(`/api/characters/${id}/cart`) && r.request().postDataJSON()?.changes?.length === 3);
  await p.getByRole("button", { name: "Add to cart" }).click();
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  await priced;
  await expect(cart.getByRole("listitem").filter({ hasText: "Add Fearful Blow" })).toContainText("20 XP");

  // A Pretender Elder learns one elder power: with one in the cart, none are left to take.
  await disciplines.getByRole("button", { name: "Add" }).click();
  await chips.getByRole("button", { name: /^Elder Disciplines/ }).click();
  await p.getByRole("button", { name: "Celerity: Projectile" }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await disciplines.getByRole("button", { name: "Add" }).click();
  await chips.getByRole("button", { name: /^Elder Disciplines/ }).click();
  await expect(chips.getByRole("button", { name: "Elder Disciplines", exact: true })).toBeVisible();
  await expect(p.getByText(/^None you can take\. \d+ you can't:/)).toBeVisible();
  await p.getByRole("button", { name: "show", exact: true }).click();
  await expect(p.getByLabel("Show")).toHaveValue("all");
  await expect(p.getByText("A Pretender Elder can learn only one elder power.", { exact: false }).first()).toBeVisible();
});

test("only a character with a ritual discipline sees rituals, up to its path's level", async ({ browser }) => {
  const { page: p } = await person(browser, "finder-ritualist");
  const id = await builtVampire(p, "Odile", "Tremere", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Thaumaturgy: Path of Blood", 2], ["Auspex", 1], ["Dominate", 1]],
  });
  const rules = await (await p.request.get("/api/rules/vampire")).json();
  const ritual = (level: number) => rules.traits.find((t: { category: string; name: string; fixed_rating: number }) => t.category === "rituals" && t.name.startsWith("Thaumaturgy: ") && t.fixed_rating === level).name as string;
  await p.goto(`/characters/${id}`);
  const disciplines = p.locator("section").filter({ has: p.getByRole("heading", { name: "Disciplines", exact: true }) });
  const chips = p.getByRole("navigation", { name: "Categories" });

  await expect(disciplines.getByRole("button", { name: /^\d+ Rituals$/ })).toBeVisible();
  await disciplines.getByRole("button", { name: /^\d+ Rituals$/ }).click();
  await expect(chips.getByRole("button", { name: /^Rituals/ })).toHaveAttribute("aria-pressed", "true");
  await p.getByLabel("Search Rituals").fill(ritual(1));
  await expect(p.getByRole("button", { name: new RegExp(`^${ritual(1)}`) })).toBeEnabled();
  // A ritual of each level comes before one of the next.
  await p.getByLabel("Search Rituals").fill(ritual(2));
  await expect(p.getByText("None you can take. 1 you can't:")).toBeVisible();
  await p.getByRole("button", { name: "show", exact: true }).click();
  await expect(p.getByText("A thaumaturge learns a ritual of each level before one of the next.", { exact: false })).toBeVisible();
  await p.getByLabel("Search Rituals").fill(ritual(3));
  // Left out of what the character can take, but a tap away, with the reason.
  await expect(p.getByText("A level 3 Thaumaturgy ritual needs a path of Thaumaturgy at 3 or more.", { exact: false })).toBeVisible();
});

test("a Tremere names Path of Corruption as the primary path, once it is the first to 2 dots", async ({ browser }) => {
  const { page: p } = await person(browser, "primary-tremere");
  const id = await builtVampire(p, "Lucita", "Tremere", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Auspex", 2], ["Thaumaturgy: Path of Blood", 1], ["Dominate", 1]],
  });
  const put = async (category: string, name: string, rating: number, detail = "") => {
    const response = await p.request.fetch(`/api/characters/${id}/traits`, { method: "PUT", headers: { "X-Horatio": "1" }, data: { category, name, rating, detail } });
    expect(response.status(), await response.text()).toBeLessThan(300);
  };
  const corruption = "Thaumaturgy: Path of Corruption";
  await put("merits", "Thaumaturgic Expertise", 1, corruption);
  await put("disciplines", corruption, 1);
  await p.goto(`/characters/${id}`);

  // The in-clan path is primary until another is named.
  const picker = p.getByLabel("Primary path of Thaumaturgy");
  await expect(picker).toHaveValue("Thaumaturgy: Path of Blood");
  await expect(picker.getByRole("option", { name: "Path of Blood (in-clan)" })).toBeAttached();
  await picker.selectOption({ label: "Path of Corruption" });
  await expect(picker).toHaveValue(corruption);

  // Named, it can reach 2 dots first, and nothing is flagged for it.
  await put("disciplines", corruption, 2);
  await p.reload();
  await expect(p.getByLabel("Primary path of Thaumaturgy")).toHaveValue(corruption);
  await expect(p.getByText("No path of Thaumaturgy can go above the primary path.")).toHaveCount(0);
  await p.screenshot(shots("primary-path-named"));

  // Path of Blood is no longer the highest, so it cannot be named back yet.
  await p.getByLabel("Primary path of Thaumaturgy").selectOption({ label: "Path of Blood (in-clan)" });
  await expect(p.getByText("Thaumaturgy: Path of Corruption is higher", { exact: false })).toBeVisible();
});

test("a player asks staff for an elder power the rules refuse, free, and a storyteller approves it", async ({ browser }) => {
  const custodian = await person(browser, "exc-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "exc-lead");
  const player = await person(browser, "exc-player");
  const troupeName = `Court of Favours ${run}`;
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;

  // Wren is built through the API, with Celerity 2, and joins the troupe.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Wren" });
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
  const asked = await send("POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  const accepted = await lead.page.request.post(`/api/approvals/${asked.id}/approve`, { headers, data: {} });
  expect(accepted.status(), await accepted.text()).toBe(200);

  // An elder power needs all five dots of its discipline: greyed in the Add panel, with a way to ask staff.
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  await part("Disciplines").getByRole("button", { name: "Add" }).click();
  await p.getByRole("navigation", { name: "Categories" }).getByRole("button", { name: /^Elder Disciplines/ }).click();
  await p.getByLabel("Search Elder Disciplines").fill("Celerity: Zephyr");
  // Left out of what Wren can take: shown greyed, with the reason, a tap away.
  await expect(p.getByText("None you can take. 1 you can't:")).toBeVisible();
  await p.getByRole("button", { name: "show", exact: true }).click();
  const row = p.getByRole("listitem").filter({ has: p.getByRole("button", { name: /^Celerity: Zephyr/ }) });
  await expect(row.getByRole("button", { name: /^Celerity: Zephyr/ })).toBeDisabled();
  await expect(row).toContainText("An elder power needs all 5 dots of its discipline first.");
  await row.getByRole("button", { name: "Ask staff" }).click();
  const ask = p.getByRole("form", { name: "Ask staff for Celerity: Zephyr" });
  await ask.getByLabel("Why").fill("A gift of the Methuselah's blood");
  await ask.getByLabel("Ask for it at no XP cost").check();
  await ask.getByRole("button", { name: "Put it in the cart" }).click();

  // In the cart it is an exception line, with the rule it breaks, and nothing to pay.
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  const line = cart.getByRole("listitem").filter({ hasText: "Add Celerity: Zephyr" });
  await expect(line.getByText("exception", { exact: true })).toBeVisible();
  await expect(line.getByText("needs approval")).toBeVisible();
  await expect(line).toContainText("Asked of staff, free: A gift of the Methuselah's blood");
  await expect(line).toContainText("Against the rules: An elder power needs all 5 dots of its discipline first.");
  await p.screenshot(shots("exception-cart"));
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Some of it waits for the home troupe's approval.")).toBeVisible();
  await expect(part("Disciplines").getByRole("button", { name: "exception asked" })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Against the rules" })).toHaveCount(0);

  // The lead finds it among the exceptions, with the rule broken and the reason, and approves it.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/approvals`);
  await l.getByLabel("Kind", { exact: true }).selectOption({ label: "Exceptions" });
  const card = l.locator("section").filter({ hasText: "Wren" });
  await expect(card.getByText("exception, free")).toBeVisible();
  await expect(card).toContainText("Celerity: Zephyr 0 → 1, asked for free");
  await expect(card).toContainText("Against the rules: An elder power needs all 5 dots of its discipline first.");
  await expect(card).toContainText("A gift of the Methuselah's blood");
  await l.screenshot(shots("exception-approval"));
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();

  // On Wren's sheet it is marked as given by exception, and its rule is not flagged.
  await p.reload();
  await expect(part("Disciplines").getByRole("button", { name: "by exception" })).toBeVisible();
  const exceptions = p.getByRole("list", { name: "Traits held by exception" });
  await expect(exceptions).toContainText("Celerity: Zephyr 1");
  await expect(exceptions).toContainText("Given by exception: approved by exc-lead");
  await expect(exceptions).toContainText(", free");
  await expect(p.getByRole("heading", { name: "Against the rules" })).toHaveCount(0);
  await part("Disciplines").getByRole("button", { name: "by exception" }).click();
  await expect(part("Disciplines")).toContainText("A gift of the Methuselah's blood");
  await p.screenshot(shots("exception-sheet"));

  // The lead gives Wren Calm Heart, which no Brujah may take: free, and despite that rule once it is shown.
  await l.goto(`/characters/${id}`);
  const merits = l.locator("section").filter({ has: l.getByRole("heading", { name: "Merits and Flaws", exact: true }) });
  await merits.getByRole("button", { name: "Give Merits and Flaws" }).click();
  await l.getByLabel("Search Merits to give").fill("Calm Heart");
  await l.getByRole("button", { name: /^Calm Heart/ }).click();
  const giving = l.getByRole("form", { name: "Give Calm Heart" });
  await giving.getByLabel("Free: at no XP cost").check();
  await giving.getByLabel("Reason").fill("Raised by a True Brujah");
  await giving.getByRole("button", { name: "Check" }).click();
  await expect(giving).toContainText("Brujah cannot take Calm Heart");
  await expect(giving.getByRole("button", { name: "Give", exact: true })).toBeDisabled();
  await giving.getByLabel("Give it despite these rules").check();
  await giving.getByRole("button", { name: "Give", exact: true }).click();
  await expect(merits.getByRole("button", { name: "by exception" })).toBeVisible();
  await expect(l.getByRole("list", { name: "Traits held by exception" })).toContainText("Given by exception: given by exc-lead");

  // Wren's player is told.
  await p.goto("/");
  await p.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(p.getByText("exc-lead gave Wren Calm Heart 1, free: Raised by a True Brujah")).toBeVisible();
});

test("a player says they committed diablerie, staff approve it, and then record another", async ({ browser }) => {
  const custodian = await person(browser, "dia-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "dia-lead");
  const player = await person(browser, "dia-player");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Sorrows ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;

  // Sable is built through the API and accepted at Generation 1.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Sable" });
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
  const asked = await send("POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  const accepted = await lead.page.request.post(`/api/approvals/${asked.id}/approve`, { headers, data: {} });
  expect(accepted.status(), await accepted.text()).toBe(200);
  const held = async (name: string) => (await (await p.request.get(`/api/characters/${id}/sheet`)).json()).traits.find((t: { name: string }) => t.name === name).rating;

  // The troupe's setting for a Lesser Generation holder starts at leaving the flaw.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/rules/starting`);
  await expect(l.getByText("Leave the flaw.")).toBeVisible();

  // The sheet has no Diablerie card: the player asks from the ⋯ menu, with the date and a note.
  await p.goto(`/characters/${id}`);
  await expect(p.getByRole("heading", { name: "Attributes", exact: true })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Diablerie", exact: true })).toHaveCount(0);
  const askStaff = async () => {
    await p.getByRole("button", { name: "More for Sable" }).click();
    await p.getByRole("menuitem", { name: "Ask staff: I committed diablerie…" }).click();
    const ask = p.getByRole("form", { name: "Ask staff about diablerie" });
    await ask.getByLabel("Date").fill("2026-10-24");
    await ask.getByLabel("Note").fill("Drank my sire at Elysium");
    return ask;
  };
  await (await askStaff()).getByRole("button", { name: "Ask staff", exact: true }).click();
  const waiting = p.getByText("Diablerie on 24 Oct 2026 waits for the storytellers.");
  await expect(waiting).toBeVisible();
  // While it waits, the menu has nothing more to ask; the player can withdraw it from the sheet.
  await p.getByRole("button", { name: "More for Sable" }).click();
  await expect(p.getByRole("menuitem", { name: "Retire…" })).toBeVisible();
  await expect(p.getByRole("menuitem", { name: /diablerie/ })).toHaveCount(0);
  await p.keyboard.press("Escape");
  await p.getByRole("button", { name: "Withdraw", exact: true }).click();
  await expect(waiting).toHaveCount(0);
  // And asks again.
  const again = await askStaff();
  await p.screenshot(shots("diablerie-ask"));
  await again.getByRole("button", { name: "Ask staff", exact: true }).click();
  await expect(waiting).toBeVisible();
  expect(await held("Generation")).toBe(1);

  // The lead sees what approving does, changes the Beast traits, and approves.
  await l.goto(`/troupes/${troupeId}/approvals`);
  await l.getByLabel("Kind", { exact: true }).selectOption({ label: "Diablerie" });
  const card = l.locator("section").filter({ hasText: "Sable" });
  await expect(card).toContainText("committed diablerie on 24 Oct 2026");
  await expect(card).toContainText("Generation background ● → ●●, as a free dot. Earlier buys keep what they cost.");
  await expect(card).toContainText("Humanity goes down 1");
  await card.getByLabel("Beast traits at the next game").fill("2");
  await card.getByLabel("Who was diablerized").fill("Her sire");
  await l.screenshot(shots("diablerie-approval"));
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();

  // Generation went up free and Humanity fell. Nothing waits now, so the sheet has nothing on
  // diablerie; the date shows behind the ⋯ menu (without the victim) and on the printed sheet.
  expect(await held("Generation")).toBe(2);
  expect(await held("Humanity")).toBe(4);
  await p.reload();
  await expect(p.getByRole("heading", { name: "Attributes", exact: true })).toBeVisible();
  await expect(waiting).toHaveCount(0);
  await expect(p.getByRole("heading", { name: "Diablerie", exact: true })).toHaveCount(0);
  await p.getByRole("button", { name: "More for Sable" }).click();
  await p.getByRole("menuitem", { name: "Ask staff: I committed diablerie…" }).click();
  await expect(p.getByRole("list", { name: "Diablerie" })).toContainText("Diablerie: 24 Oct 2026");
  await expect(p.getByRole("list", { name: "Diablerie" })).not.toContainText("Her sire");
  await p.goto(`/print/characters/${id}`);
  await expect(p.getByText("Diablerie: 24 Oct 2026")).toBeVisible();
  // Two Beast traits wait for the next game on the Play View.
  expect((await (await p.request.get(`/api/characters/${id}/play`)).json()).beast.value).toBe(2);

  // The lead opens Record diablerie from the ⋯ menu, and sees who was diablerized.
  await l.goto(`/characters/${id}`);
  await expect(l.getByRole("heading", { name: "Attributes", exact: true })).toBeVisible();
  await expect(l.getByRole("heading", { name: "Diablerie", exact: true })).toHaveCount(0);
  const recordDiablerie = async () => {
    await l.getByRole("button", { name: "More for Sable" }).click();
    await l.getByRole("menuitem", { name: "Record diablerie…" }).click();
    return l.getByRole("dialog", { name: "Record diablerie for Sable" });
  };
  await expect((await recordDiablerie()).getByRole("list", { name: "Diablerie" })).toContainText("Her sire");
  await l.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(l.getByRole("dialog")).toHaveCount(0);
  // And records another, taking more Humanity than filled in.
  const dialog = await recordDiablerie();
  const form = dialog.getByRole("form", { name: "Record diablerie" });
  await form.getByLabel("Date").fill("2026-10-25");
  await form.getByLabel("Who was diablerized").fill("The Prince");
  await expect(form).toContainText("Generation background ●● → ●●●, as a free dot.");
  await form.getByLabel("Humanity lowered by").fill("2");
  await expect(form).toContainText("Humanity goes down 2, with no XP back.");
  await l.screenshot(shots("diablerie-record"));
  await form.getByRole("button", { name: "Record diablerie" }).click();
  await expect(dialog).toBeHidden();
  await expect((await recordDiablerie()).getByRole("list", { name: "Diablerie" })).toContainText("Diablerie: 25 Oct 2026");
  expect(await held("Generation")).toBe(3);
  expect(await held("Humanity")).toBe(2);
});

test("a skill's specialisations sit in its own list item, in the sheet's two columns and on a phone", async ({ browser }) => {
  const { page: p } = await person(browser, "stay-together");
  const id = await builtVampire(p, "Marguerite", "Toreador", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Auspex", 2], ["Celerity", 1], ["Presence", 1]],
    skills: ATTRIBUTES_AND_FOCUSES.skills.map(([name, rating]) => [name === "Medicine" ? "Academics" : name, rating]),
  });
  await p.goto(`/characters/${id}`);
  const skills = p.locator("section").filter({ has: p.getByRole("heading", { name: "Skills", exact: true }) });
  const academics = skills.locator("li[data-trait='Academics']");
  for (const width of [1280, 390]) {
    await p.setViewportSize({ width, height: 900 });
    // Name one specialisation for Academics.
    if (width === 1280) {
      await academics.getByRole("button", { name: "Add to Academics Specializations" }).click();
      await academics.getByLabel("Name a Academics Specializations").fill("Medieval");
      await academics.getByRole("button", { name: "Add", exact: true }).click();
    }
    // The skill, its specialisations and their Add button all sit in the one item.
    await expect(academics.getByText("Academics", { exact: true }).first()).toBeVisible();
    await expect(academics.getByText("Academics Specializations 1/1")).toBeVisible();
    await expect(academics.getByRole("button", { name: "Remove Medieval" })).toBeVisible();
    await expect(academics.getByRole("listitem")).toHaveCount(0); // one item for the whole trait
    // And the item is kept whole across a column break.
    await expect(academics).toHaveCSS("break-inside", "avoid");
  }
  await p.screenshot(shots("specializations-stay-together"));
});

test("on a phone the − and + are big enough to tap, apart, and a greyed − says why when tapped (#361)", async ({ browser }) => {
  const { page: p } = await person(browser, "thumb-steps");
  const id = await builtVampire(p, "Ysolde", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Generation", 1], ["Herd", 2], ["Fame", 3]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  await p.goto(`/characters/${id}`);
  const lower = p.getByRole("button", { name: "Lower Brawl" });
  const raise = p.getByRole("button", { name: "Raise Brawl" });
  await expect(raise).toBeVisible();

  // At least 40px on a touch screen, with room between them; the desktop keeps its compact rows.
  const minus = (await lower.boundingBox())!;
  const plus = (await raise.boundingBox())!;
  if (test.info().project.name === "phone") {
    for (const box of [minus, plus]) {
      expect(box.width).toBeGreaterThanOrEqual(40);
      expect(box.height).toBeGreaterThanOrEqual(40);
    }
    expect(plus.x - (minus.x + minus.width)).toBeGreaterThanOrEqual(12);
  } else expect(minus.height).toBeLessThan(40);

  // Brawl 4 is all from creation, so − is greyed. Its reason is no hover title: a tap shows it, and nothing goes in the cart.
  const why = "These dots were free, not bought with XP; only storytellers can take them away.";
  await expect(lower).toBeDisabled();
  await expect(lower).toHaveAccessibleDescription(why);
  const reason = p.locator(`[id="${await lower.getAttribute("aria-describedby")}"]`);
  await expect(reason).toBeHidden();
  // Forced: Playwright won't click what is greyed, but a thumb can.
  await lower.click({ force: true });
  await expect(reason).toHaveText(why);
  await expect(reason).toBeInViewport();
  await p.screenshot(shots("greyed-minus-why"));
  await expect(p.getByRole("list", { name: "Changes in the cart" })).toHaveCount(0);
});

test("an attribute stops rising at the limit Generation gives", async ({ browser }) => {
  const { page: p } = await person(browser, "limit-player");
  // A Neonate may take one attribute to 11 (core p. 102).
  const id = await builtVampire(
    p,
    "Stoddard",
    "Brujah",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 1], ["Herd", 2], ["Fame", 3]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] },
    [["attributes", "Physical", 10]],
  );
  await p.goto(`/characters/${id}`);
  const cart = p.getByRole("list", { name: "Changes in the cart" });

  // One dot to 11 is fine for a Neonate; the next is refused on its line, and nothing can be spent.
  await p.getByRole("button", { name: "Raise Physical" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Physical 10 → 11" })).not.toContainText("Generation rating");
  await expect(p.getByRole("button", { name: "Spend XP" })).toBeEnabled();
  await p.getByRole("button", { name: "Raise Physical" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Physical 10 → 12" })).toContainText("only as many dots, in all, as the Generation rating");
  await expect(p.getByRole("button", { name: "Spend XP" })).toBeDisabled();
  // Stepping back to 11 makes it fine again.
  await p.getByRole("button", { name: "Lower Physical" }).click();
  await expect(p.getByRole("button", { name: "Spend XP" })).toBeEnabled();
});

test("a player says who each Retainer bought is, and a storyteller links one to an NPC", async ({ browser }) => {
  const custodian = await person(browser, "ret-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "ret-lead");
  const owner = await person(browser, "ret-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Retinue Row ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);

  // Dorothea, at home in the troupe with Marta as a Retainer at 3, and staff give her Pike at 1.
  const { id } = await send(owner.page, "POST", "/api/characters", { splat: "vampire", name: "Dorothea" });
  await send(owner.page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const picks: Record<string, [string, number, string?][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Retainers", 3, "Marta, the driver"], ["Haven", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, list] of Object.entries(picks))
    await send(owner.page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating, detail]) => ({ name: n, rating, detail: detail ?? "" })) });
  await send(owner.page, "POST", `/api/characters/${id}/creation/complete`);
  const asked = await send(owner.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  await send(lead.page, "POST", `/api/characters/${id}/give`, { category: "backgrounds", name: "Retainers", detail: "Pike", rating: 1, free: true, reason: "A second Retainer" });
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Marta Voss", wizard: false });

  // Both are listed, under the last of them, with the dots bought for each.
  const p = owner.page;
  await p.goto(`/characters/${id}`);
  const list = p.getByLabel("Retainers list");
  await expect(list).toHaveCount(1);
  await expect(list.getByRole("list", { name: "Retainers" }).getByRole("listitem")).toHaveCount(2);
  // The player says who Marta is; her name and dots are the sheet's.
  await list.getByRole("button", { name: "Edit Retainers" }).click();
  await expect(list.getByLabel("Retainer name")).toHaveCount(0);
  await list.getByLabel("About Marta, the driver").fill("Drives at night");
  await list.getByRole("button", { name: "Save Retainers" }).click();
  await expect(list.getByText("Drives at night")).toBeVisible();
  await expect(list.getByRole("button", { name: /^NPC for/ })).toHaveCount(0);
  await p.screenshot(shots("retainers"));

  // Both show on the printed sheet and the Play View.
  await p.goto(`/print/characters/${id}`);
  await expect(p.getByRole("article", { name: "Retainer: Marta, the driver" })).toContainText("Drives at night");
  await expect(p.getByRole("article", { name: "Retainer: Pike" })).toContainText("Pool 2");
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Sheet" }).click();
  const playing = p.getByRole("list", { name: "Retainers" });
  await expect(playing.getByText("Marta, the driver")).toBeVisible();
  await expect(playing.getByText("Pike")).toBeVisible();

  // A storyteller links Marta to the NPC, and the link opens it.
  const l = lead.page;
  await l.goto(`/characters/${id}`);
  const his = l.getByLabel("Retainers list");
  await his.getByRole("button", { name: "Edit Retainers" }).click();
  await his.getByLabel("NPC for Marta, the driver").selectOption({ label: "Marta Voss" });
  await his.getByRole("button", { name: "Save Retainers" }).click();
  await his.getByRole("link", { name: "Marta Voss" }).click();
  await expect(l.getByRole("heading", { name: "Marta Voss" }).first()).toBeVisible();

  // The change is on the character's log.
  await l.goto(`/characters/${id}/log`);
  await expect(l.getByText("ret-lead linked Marta, the driver, one of Dorothea (ret-player)'s Retainers, to an NPC.")).toBeVisible();

  // Pike is killed: the sheet says when his dot comes back (a game, and two
  // weeks), and his block on the Play View is greyed out until then.
  await p.goto(`/characters/${id}`);
  await list.getByRole("button", { name: "Edit Retainers" }).click();
  await list.getByLabel("Status of Pike").selectOption("killed");
  await list.getByRole("button", { name: "Save Retainers" }).click();
  await expect(list.getByText(/^Its dots come back once 1 game has gone by since, and not before /)).toBeVisible();
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Tracker" }).click();
  const pike = p.getByRole("article", { name: "Retainer: Pike" });
  await expect(pike).toHaveAttribute("aria-disabled", "true");
  await expect(pike.getByRole("status")).toContainText("Killed");
  await expect(pike.getByRole("button", { name: "Spend Pike: health" })).toBeDisabled();
  await expect(p.getByRole("article", { name: "Retainer: Marta, the driver" }).getByRole("button", { name: "Spend Marta, the driver: health" })).toBeEnabled();
});
