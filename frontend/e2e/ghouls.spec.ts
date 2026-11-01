import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, ATTRIBUTES_AND_FOCUSES, backstoryOptional, characterTab } from "./support";

/** Ghouls: building, playing and Embracing them. */

closeContextsAfterEach();

test("a troupe takes ghouls once its storytellers tick Ghoul on About, and a ghoul can then join", async ({ browser }) => {
  const custodian = await person(browser, "splat-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "splat-lead");
  const player = await person(browser, "splat-player");
  const troupeName = `Thrall Court ${run}`;
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

  // A player builds a ghoul, bound to a domitor not in Horatio; the troupe takes vampires only.
  const p = player.page;
  const send = (method: "POST" | "PUT", url: string, data: object) => p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
  const made = await send("POST", "/api/characters", { splat: "ghoul", name: "Renfield", domitor: { name: "Count Orlok", clan: "Nosferatu" } });
  expect(made.status(), await made.text()).toBe(201);
  const { id } = await made.json();
  const refused = await send("POST", `/api/characters/${id}/troupes`, { troupe_id: troupeId });
  expect(refused.status()).toBe(409);
  expect((await refused.json()).detail).toBe(`${troupeName} does not take ghoul characters.`);

  // The lead ticks Ghoul, in Customise's Troupe settings. Vampire, the only splat ticked until then, could not be unticked.
  await l.getByRole("link", { name: "Customise", exact: true }).click();
  await l.getByRole("link", { name: "Troupe settings", exact: true }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/settings$`));
  const splats = l.locator("section").filter({ has: l.getByRole("heading", { name: "Splats", exact: true }) });
  await expect(splats.getByRole("checkbox", { name: "Vampire" })).toBeChecked();
  await expect(splats.getByRole("checkbox", { name: "Vampire" })).toBeDisabled();
  await expect(splats.getByRole("checkbox", { name: "Ghoul" })).not.toBeChecked();
  // The box follows the troupe as saved, so it ticks once the change is in.
  await splats.getByRole("checkbox", { name: "Ghoul" }).click();
  await expect(splats.getByRole("checkbox", { name: "Ghoul" })).toBeChecked();
  await expect(splats.getByRole("checkbox", { name: "Vampire" })).toBeEnabled();
  await l.reload();
  await expect(splats.getByRole("checkbox", { name: "Ghoul" })).toBeChecked();

  // Now the ghoul joins, and the player reads which splats may.
  const joined = await send("POST", `/api/characters/${id}/troupes`, { troupe_id: troupeId });
  expect(joined.status(), await joined.text()).toBe(201);
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByText("Vampire and Ghoul player characters may join.")).toBeVisible();
});

test("a player builds a ghoul in the wizard, bound to their own vampire, and later moves its dots to a new domitor", async ({ browser }) => {
  test.slow();
  const custodian = await person(browser, "ghw-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "ghw-lead");
  const player = await person(browser, "ghw-player");
  const takesGhouls = `Blood Bond Court ${run}`;
  const vampiresOnly = `Pure Blood Court ${run}`;
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT" | "PATCH", url: string, data: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id: ghoulCourt } = await send(custodian.page, "POST", "/api/troupes", { name: takesGhouls, lead_handle: lead.handle });
  await send(custodian.page, "POST", "/api/troupes", { name: vampiresOnly, lead_handle: lead.handle });
  await send(lead.page, "PATCH", `/api/troupes/${ghoulCourt}`, { allowed_splats: ["vampire", "ghoul"] });

  // The player's Toreador, who will be the domitor: Auspex 2, Celerity 1, Presence 1.
  const p = player.page;
  const { id: domitorId } = await send(p, "POST", "/api/characters", { splat: "vampire", name: "Lady Ysolde" });
  await send(p, "PUT", `/api/characters/${domitorId}/traits`, { category: "clan", name: "Toreador", rating: null });
  await send(p, "PUT", `/api/characters/${domitorId}/creation/categories/disciplines`, {
    picks: [
      { name: "Auspex", rating: 2 },
      { name: "Celerity", rating: 1 },
      { name: "Presence", rating: 1 },
    ],
  });

  // Built for a troupe that takes vampires only, a new character cannot be a ghoul.
  await p.reload();
  await p.getByLabel("Name").fill("Wendel");
  await p.getByLabel("Which troupe will you play in?").selectOption({ label: vampiresOnly });
  await expect(p.getByLabel("Splat").locator("option")).toHaveText(["Vampire"]);
  await expect(p.getByText(`${vampiresOnly} takes vampire characters only.`)).toBeVisible();
  await p.getByLabel("Which troupe will you play in?").selectOption({ label: takesGhouls });
  await expect(p.getByLabel("Splat").locator("option")).toHaveText(["Vampire", "Ghoul"]);
  await p.getByLabel("Splat").selectOption("Ghoul");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const ghoulId = new URL(p.url()).pathname.split("/")[2]!;

  // Review says the domitor is missing, and Finish waits for it.
  await p.getByRole("link", { name: /Review/ }).click();
  await expect(p.getByRole("region", { name: "Still to settle" }).getByText(/Choose the domitor/)).toBeVisible();
  await expect(p.getByRole("button", { name: "Finish creation" })).toBeDisabled();

  // On Concept the domitor takes the place of the clan.
  await p.getByRole("region", { name: "Still to settle" }).getByRole("link", { name: "Go to Concept" }).click();
  await expect(p.getByLabel("Clan", { exact: true })).toHaveCount(0);
  const domitor = p.getByRole("region", { name: "Domitor" });
  await domitor.getByLabel("Find a vampire").fill("ysol");
  await domitor.getByRole("radio", { name: /Lady Ysolde/ }).check();
  await expect(domitor.getByText("Wendel's in-clan disciplines would be the domitor's: Auspex, Celerity and Presence.")).toBeVisible();
  await domitor.getByRole("button", { name: "Save domitor" }).click();
  await expect(domitor.getByText("Bound to Lady Ysolde, Toreador.")).toBeVisible();
  await expect(p.getByText("In-clan now: Auspex, Celerity and Presence.")).toBeVisible();

  // The other steps through the API; no Generation among the backgrounds.
  const build: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Herd", 2], ["Allies", 1]],
  };
  for (const [category, picks] of Object.entries(build))
    await send(p, "PUT", `/api/characters/${ghoulId}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await p.goto(`/characters/${ghoulId}/create/backgrounds`);
  await expect(p.getByRole("button", { name: "Fame 3", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(p.getByRole("button", { name: "About Generation" })).toHaveCount(0);

  // 5 dots, in-clan only, none higher than Lady Ysolde has; the rest saved for later.
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Disciplines", exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(p.getByText(/A ghoul has 5 dots of disciplines, all in its domitor's in-clan disciplines, no higher than your domitor has each/)).toBeVisible();
  await expect(p.getByRole("button", { name: "Potence 1", exact: true })).toHaveCount(0);
  // Each rating is asked of the server, which takes a while on a busy one.
  await expect(p.getByRole("button", { name: "Celerity 2", exact: true })).toBeDisabled({ timeout: 15_000 });
  await expect(p.getByText(/Not at 2, 3, 4 or 5: The domitor does not have Celerity that high/)).toBeVisible();
  await p.getByRole("button", { name: "Auspex 2", exact: true }).click();
  await p.getByRole("button", { name: "Celerity 1", exact: true }).click();
  const placed = p.getByRole("list", { name: "Disciplines dots placed" });
  await expect(placed).toContainText("3 of 5 placed");
  await expect(placed).toContainText("2 saved for later");
  await expect(p.getByText(/2 dots are saved for later\. They are kept after creation, and placed later the same way/)).toBeVisible();

  // A merit about the vampiric condition is left out, and refused with its reason.
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Merits & flaws", exact: true })).toBeVisible({ timeout: 15_000 });
  const merits = p.getByRole("region", { name: "Merits", exact: true });
  await merits.getByLabel("Search Merits").fill("Calm Heart");
  await expect(merits.getByText("Calm Heart", { exact: true })).toHaveCount(0);
  await merits.getByLabel("Show Merits").selectOption({ label: "Everything" });
  await expect(merits.getByText("Calm Heart is about the vampiric condition, so a ghoul cannot take it.")).toBeVisible();
  await expect(merits.getByRole("checkbox", { name: /Calm Heart/ })).toBeDisabled();

  // Review lists the domitor and the dots saved, and finishing opens the sheet.
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(p.getByText("3 of 5 dots placed, 2 saved for later", { exact: false })).toBeVisible();
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p).toHaveURL(new RegExp(`/characters/${ghoulId}$`));
  const card = p.locator("section").filter({ has: p.getByRole("heading", { name: "Domitor", exact: true }) });
  await expect(card.getByText("Bound to Lady Ysolde, Toreador.")).toBeVisible();
  await expect(card.getByText("In-clan disciplines, the domitor's: Auspex, Celerity and Presence.")).toBeVisible();

  // Until a troupe accepts Wendel, the player binds him to another domitor, and moves his dots.
  await card.getByRole("button", { name: "Change domitor" }).click();
  await card.getByRole("radio", { name: "Not in Horatio" }).check();
  await card.getByLabel("Domitor's name").fill("Old Marta");
  await card.getByLabel("Domitor's clan").selectOption("Ventrue");
  await card.getByRole("radio", { name: "Move them all to the new domitor's in-clan disciplines" }).check();
  await card.getByLabel("Presence", { exact: true }).selectOption("2");
  await expect(card.getByText("Move all 3 dots; 2 are placed.")).toBeVisible();
  await card.getByLabel("Dominate", { exact: true }).selectOption("1");
  await card.getByRole("button", { name: "Save domitor" }).click();
  await expect(card.getByText("Bound to Old Marta, Ventrue, who is not in Horatio.")).toBeVisible();
  await expect(card.getByText("In-clan disciplines, the domitor's: Dominate, Fortitude and Presence.")).toBeVisible();
  const traits = await (await p.request.get(`/api/characters/${ghoulId}/sheet`)).json();
  expect(Object.fromEntries(traits.traits.filter((t: { category: string }) => t.category === "disciplines").map((t: { name: string; rating: number }) => [t.name, t.rating]))).toEqual({
    Dominate: 1,
    Presence: 2,
  });
});

test("a ghoul with Stolen Potential naming Mental takes no Mental focus, and finishes (#312)", async ({ browser }) => {
  const { page: p } = await person(browser, "thrall-stolen");
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "ghoul", name: "Hollow Thrall", domitor: { name: "Count Orlok", clan: "Nosferatu" } });
  // Every pick but a Mental focus.
  const build = Object.entries({ ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Resources", 2], ["Allies", 1]] }).filter(([category]) => category !== "focus_mentals");
  for (const [category, picks] of build as [string, [string, number][]][])
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });

  await p.goto(`/characters/${id}/create/merits`);
  const flaw = p.getByRole("checkbox", { name: /^Stolen Potential/ });
  await flaw.scrollIntoViewIfNeeded();
  await flaw.check();
  await p.getByLabel("Stolen Potential: which?").selectOption("Mental");
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });
  // Nothing waits on a Mental focus.
  await expect(p.getByText(/Mental Focus at 1/)).toHaveCount(0);

  // Focuses says why there is none, as a vampire's does.
  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Focuses/ }).click();
  await expect(p.getByText("Stolen Potential: no Mental focus (p. 265).")).toBeVisible();
  await expect(p.getByRole("button", { name: "Wits 1" })).toHaveCount(0);

  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Review/ }).click();
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  await expect(p.getByText("Stolen Potential: Mental").first()).toBeVisible();
  await expect(p.getByText("Mental Focus", { exact: true })).toHaveCount(0);
});

test("a ghoul at a game spends vitae but never its human Blood, drinks vitae, and has no Beast or frenzy", async ({ browser }) => {
  const custodian = await person(browser, "vitae-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "vitae-lead");
  const player = await person(browser, "vitae-player");
  await custodian.page.reload();
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT" | "PATCH", url: string, data: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: `Vitae Court ${run}`, lead_handle: lead.handle });
  await send(lead.page, "PATCH", `/api/troupes/${troupeId}`, { allowed_splats: ["vampire", "ghoul"] });
  const p = player.page;
  const { id } = await send(p, "POST", "/api/characters", { splat: "ghoul", name: "Mina Harker", domitor: { name: "Count Orlok", clan: "Nosferatu" } });
  await send(p, "POST", `/api/characters/${id}/troupes`, { troupe_id: troupeId });

  // Its Blood is 5 vitae, which it spends, and 5 human Blood, which it can't.
  await p.goto(`/play/characters/${id}?tab=tracker`);
  const blood = p.getByRole("region", { name: "Blood" });
  await expect(blood.getByLabel("Vitae: 5 of 5")).toBeVisible();
  await expect(blood.getByLabel("Human Blood", { exact: true }).first()).toBeVisible();
  await expect(blood.getByRole("button", { name: "Human Blood" })).toHaveCount(0);
  await blood.getByRole("button", { name: "Spend Vitae" }).last().click();
  await expect(blood.getByLabel("Vitae: 4 of 5")).toBeVisible();
  await expect(blood.getByText("5 human Blood, which can't be spent.", { exact: false })).toBeVisible();
  await expect(p.getByText("Vitae 5 → 4")).toBeVisible();
  // The domitor, and the clan weakness it plays for roleplay only.
  await expect(p.getByText("Domitor: Count Orlok")).toBeVisible();
  await expect(p.getByText(/Weakness: A milder form of the Nosferatu weakness, for roleplay only/).first()).toBeVisible();

  // Drank vitae fills it again, and the monthly drink counts from now.
  await expect(blood.getByText(/No drink of vitae recorded yet/)).toBeVisible();
  await blood.getByRole("button", { name: "Drank vitae" }).click();
  await blood.getByRole("button", { name: "Save" }).click();
  await expect(blood.getByLabel("Vitae: 5 of 5")).toBeVisible();
  await expect(p.getByText("Drank 1 vitae: Vitae 4 → 5")).toBeVisible();
  await expect(blood.getByText("Last drank vitae today.")).toBeVisible();

  // No Beast traits, frenzy or Feed: a ghoul is mortal (MET: VtM core p. 297).
  await expect(p.getByRole("heading", { name: "Beast traits" })).toHaveCount(0);
  await expect(p.getByText("Frenzy", { exact: true })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Feed" })).toHaveCount(0);

  // Its printed sheet has boxes for both.
  await p.goto(`/print/characters/${id}`);
  await expect(p.getByText("Vitae: up to 5 · 1 per turn")).toBeVisible();
  await expect(p.getByRole("img", { name: "Human Blood: 5 boxes" })).toBeVisible();

  // The troupe's roster, with the ghoul on it, still loads.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/characters`);
  await expect(l.getByRole("link", { name: "Mina Harker" })).toBeVisible();
  await expect(l.getByText("Nosferatu · Ghoul")).toBeVisible();
});

test("staff Embrace a ghoul: it becomes a vampire in XP debt, the cart waits, and an award pays the debt", async ({ browser }) => {
  test.slow();
  const custodian = await person(browser, "emb-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "emb-lead");
  const player = await person(browser, "emb-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT" | "PATCH", url: string, data: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: `Court of the Childe ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupeId);
  await send(lead.page, "PATCH", `/api/troupes/${troupeId}`, { allowed_splats: ["vampire", "ghoul"] });

  // The book's Vivian (p. 299): an Assamite Vizier's ghoul with Uncommon Clan and Code of
  // Honor, Auspex 3 and Quietus 2, all her creation XP spent, and accepted.
  const p = player.page;
  const { id } = await send(p, "POST", "/api/characters", {
    splat: "ghoul",
    name: "Vivian",
    building_troupe_id: troupeId,
    domitor: { name: "The Vizier", clan: "Assamite: Vizier" },
  });
  // In the Camarilla, as the book has her: its Assamites are Viziers, so the clan gives
  // her Uncommon Clan alone (p. 403, #313).
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
  const build: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Herd", 2], ["Allies", 1]],
    disciplines: [["Auspex", 3], ["Quietus", 2]],
    merits: [["Uncommon Clan", 2], ["Code of Honor", 2]],
  };
  for (const [category, picks] of Object.entries(build))
    await send(p, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send(p, "POST", `/api/characters/${id}/creation/complete`, {});
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "attributes", name: "Mental", rating: 10 });
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "attributes", name: "Social", rating: 8 });
  const asked = await send(p, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});

  // The lead Embraces her from her sheet, a step at a time, by a Malkavian not in Horatio.
  const l = lead.page;
  await l.goto(`/characters/${id}`);
  await l.getByRole("button", { name: "Embrace…" }).click();
  const form = l.getByRole("form", { name: "Embrace" });
  await expect(form.getByRole("radio", { name: "Vivian becomes a vampire" })).toBeChecked();
  await form.getByLabel("Date").fill("2026-10-24");
  await form.getByRole("button", { name: "Next" }).click();
  await form.getByRole("radio", { name: "Not in Horatio" }).check();
  await form.getByLabel("Sire's name").fill("Doctor Mirth");
  await form.getByLabel("Sire's clan").selectOption("Malkavian");
  await form.getByLabel("Sire's generation").fill("10");
  await expect(form.getByText("Vivian would be a vampire of Malkavian, 11th generation. In-clan: Auspex, Dementation and Obfuscate.")).toBeVisible();
  await form.getByRole("button", { name: "Next" }).click();
  const step = form.getByLabel("This step");
  await expect(step).toContainText("Uncommon Clan stripped, its XP refunded");
  await expect(step).toContainText("After it: 2 XP");
  await form.getByRole("button", { name: "Next" }).click();
  await expect(step).toContainText("After it: 1 XP");
  await form.getByRole("button", { name: "Next" }).click();
  await expect(step).toContainText("Quietus 2 lost, as every ghoul dot is");
  await expect(step).toContainText("Auspex 2, free");
  await form.getByRole("button", { name: "Next" }).click();
  await form.getByRole("button", { name: "Next" }).click();
  await form.getByLabel("Clan weakness").fill("Her derangement: paranoia");
  await form.getByRole("checkbox", { name: /Take off Code of Honor/ }).check();
  await expect(step).toContainText("After it: 3 XP");
  await form.getByRole("button", { name: "Next" }).click();
  // She keeps 2 dots of Quietus, out of clan for 12 XP, into debt as the Storyteller allows.
  await form.getByLabel("Quietus, was 2").selectOption("2");
  await form.getByRole("checkbox", { name: /The Storyteller lets lost dots be bought back into XP debt/ }).check();
  await expect(step).toContainText("Quietus 0 → 2 bought back, no teacher needed");
  await expect(step).toContainText("After it: 9 XP owed");
  await form.getByRole("button", { name: "Next" }).click();
  await expect(form).toContainText("0 XP before; 9 XP owed after.");
  await l.screenshot(shots("embrace-confirm"));
  await form.getByRole("button", { name: "Embrace Vivian" }).click();
  await expect(l.getByRole("list", { name: "Embrace" })).toContainText("Embraced 24 Oct 2026 by Doctor Mirth, of Malkavian, 10th generation.");

  // Her sheet is a vampire's, with the debt shown.
  await p.goto(`/characters/${id}`);
  await expect(p.getByText("XP debt: 9. The XP Vivian earns pays it off first, and nothing new can be bought until it has.")).toBeVisible();
  await expect(p.getByText("vampire", { exact: true })).toBeVisible();
  await p.screenshot(shots("embrace-sheet"));
  // The cart refuses what costs XP while she owes it.
  await p.getByRole("button", { name: "Raise Brawl" }).click();
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  await expect(cart).toContainText("The character owes 9 XP of debt.");
  await expect(p.getByRole("button", { name: "Spend XP" })).toBeDisabled();

  // An award pays the debt first, and the XP history says so.
  await send(l, "POST", `/api/characters/${id}/xp`, { amount: 14, reason: "Game, 31 October" });
  // The cart keeps Brawl while she looks at her XP history on its own tab.
  await characterTab(p, "Experience");
  const award = p.getByRole("row").filter({ hasText: "Game, 31 October" });
  await expect(award).toContainText("9 XP to the debt; it is paid off");
  await characterTab(p, "Sheet");
  await expect(cart).toContainText("Brawl 4 → 5");
  await expect(p.getByText(/XP debt: /)).toHaveCount(0);
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 5 XP.")).toBeVisible();
});
