import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, backstoryOptional } from "./support";

/** Status and titles, on the sheet, on badges and at a game. */

closeContextsAfterEach();

test("a player keeps their own sect status, naming its patron from the home troupe, until the troupe gives it to staff only", async ({ browser }) => {
  const custodian = await person(browser, "status-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "status-lead");
  const player = await person(browser, "status-player");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Standing ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };

  // Celestine, a Camarilla Brujah, built through the API and accepted home.
  const p = player.page;
  const { id } = await send(p, "POST", "/api/characters", { splat: "vampire", name: "Celestine" });
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
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
    await send(p, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send(p, "POST", `/api/characters/${id}/creation/complete`, {});
  const asked = await send(p, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});

  // The troupe's NPCs: its Prince, an untitled one, and a Sabbat Bishop.
  for (const [name, sect, title] of [["Prince Aurelio", "Camarilla", "Prince"], ["Udo the Quiet", "Camarilla", null], ["Bishop Corvin", "Sabbat", "Bishop"]] as const) {
    const npc = await send(lead.page, "POST", `/api/troupes/${troupeId}/npcs`, { name, wizard: false });
    await send(lead.page, "PUT", `/api/characters/${npc.id}/npc/ratings`, { category: "sect", name: sect, rating: null, detail: "" });
    if (title) await send(lead.page, "PUT", `/api/troupes/${troupeId}/characters/${npc.id}/titles`, { titles: [title] });
  }

  // On the character's Status & Titles tab: Accepted, and no fleeting status yet.
  await p.goto(`/characters/${id}`);
  await p.getByRole("link", { name: "Status & Titles", exact: true }).click();
  const card = p.locator("section").filter({ has: p.getByRole("heading", { name: "Status", exact: true }) });
  await expect(card.getByRole("listitem", { name: "Acknowledged" })).toContainText("by the Camarilla");
  await expect(card.getByText("Fleeting: 0 of 5")).toBeVisible();

  // Celestine is given Loyal by the Prince, picked from the home troupe's characters.
  await card.getByRole("button", { name: "Add status" }).click();
  const form = p.getByRole("form", { name: "Add status" });
  await form.getByLabel("Status").selectOption("Loyal");
  await form.getByRole("combobox", { name: "A character" }).click();
  const patrons = p.getByRole("listbox", { name: "Patrons" });
  await expect(patrons.getByRole("option")).toHaveText(["Prince Aurelio (Prince)NPC"]);
  await form.getByRole("combobox", { name: "A character" }).fill("aur");
  await patrons.getByRole("option", { name: /Prince Aurelio/ }).click();
  await form.getByLabel("The story (optional)").fill("For keeping the Masquerade at the docks");
  await p.screenshot(shots("status-add"));
  await form.getByRole("button", { name: "Add status" }).click();
  await expect(card.getByText("from Prince Aurelio (Prince at the time)")).toBeVisible();
  await expect(card.getByText("Fleeting: 1 of 5")).toBeVisible();
  await expect(card.getByText("For keeping the Masquerade at the docks")).toBeVisible();
  await p.screenshot(shots("status-sheet"));

  // Taken off again, and both in the character's log.
  await card.getByRole("button", { name: "Remove Loyal" }).click();
  await expect(card.getByText("Fleeting: 0 of 5")).toBeVisible();
  await p.getByRole("link", { name: "Log", exact: true }).click();
  await expect(p.getByText("status-player gave Celestine the fleeting status Loyal, from Prince Aurelio (Prince at the time).")).toBeVisible();
  await expect(p.getByText("status-player removed Celestine's Loyal (from Prince Aurelio (Prince at the time)).")).toBeVisible();

  // The lead gives status to staff only, on the troupe's About tab.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}`);
  const setting = l.locator("section").filter({ has: l.getByRole("heading", { name: "Status on sheets" }) });
  await expect(setting.getByText("Players keep their own.")).toBeVisible();
  await setting.getByRole("button", { name: "Change who keeps status on sheets" }).click();
  await setting.getByLabel(/Staff only/).check();
  await setting.getByRole("button", { name: "Save" }).click();
  await expect(setting.getByText("Staff only.")).toBeVisible();

  // Now Celestine's player cannot add status, and the API refuses them.
  await p.goto(`/characters/${id}/status`);
  await expect(card.getByText("Fleeting: 0 of 5")).toBeVisible();
  await expect(card.getByRole("button", { name: "Add status" })).toHaveCount(0);
  const refused = await p.request.post(`/api/characters/${id}/status`, { headers, data: { name: "Loyal", patron_text: "The Prince" } });
  expect(refused.status()).toBe(409);
});

test("Status & Titles: a Camarilla player sees the status held with its sources, takes Harpy from the titles sidebar and gains its status, switches to Keeper of Elysium, and opens a status ban, on desktop and phone (#321, #339)", async ({ browser }) => {
  const custodian = await person(browser, "stitles-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "stitles-lead");
  const player = await person(browser, "stitles-player");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Titles ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };

  // Lady Vasquez, a Camarilla Gangrel (not of a pillar clan: a lesser status ban), built
  // through the API and accepted home.
  const p = player.page;
  const { id } = await send(p, "POST", "/api/characters", { splat: "vampire", name: "Lady Vasquez" });
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Gangrel", rating: null });
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
  const build: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Animalism", 2], ["Fortitude", 1], ["Protean", 1]],
  };
  for (const [category, picks] of Object.entries(build))
    await send(p, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send(p, "POST", `/api/characters/${id}/creation/complete`, {});
  const asked = await send(p, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});
  // The troupe's Prince, an NPC.
  const prince = await send(lead.page, "POST", `/api/troupes/${troupeId}/npcs`, { name: "Mirela Stoica", wizard: false });
  await send(lead.page, "PUT", `/api/characters/${prince.id}/npc/ratings`, { category: "sect", name: "Camarilla", rating: null, detail: "" });
  await send(lead.page, "PUT", `/api/troupes/${troupeId}/characters/${prince.id}/titles`, { titles: ["Prince"] });
  // Loyal, from the Prince.
  await send(p, "POST", `/api/characters/${id}/status`, { name: "Loyal", patron_id: prince.id, patron_text: "", place: "Elysium", story: "For holding the door" });

  // The status held is the main column, a line each with its type and where it comes
  // from; the titles are a sidebar beside it, listing the troupe's Camarilla titles,
  // each with the status it gives.
  await p.goto(`/characters/${id}`);
  await p.getByRole("link", { name: "Status & Titles", exact: true }).click();
  const titles = p.getByRole("complementary", { name: "Titles" });
  const choices = titles.getByRole("region", { name: "Titles to choose" });
  const held = titles.getByRole("region", { name: "Titles held" });
  const status = p.locator("section").filter({ has: p.getByRole("heading", { name: "Status", exact: true }) });
  const list = status.getByRole("list", { name: "Status held" });
  const line = (name: string) => list.getByRole("listitem", { name, exact: true });
  await expect(line("Acknowledged").getByText("accepted", { exact: true })).toBeVisible();
  await expect(line("Acknowledged")).toContainText("by the Camarilla");
  await expect(line("Loyal").getByText("fleeting", { exact: true })).toBeVisible();
  await expect(line("Loyal")).toContainText("from Mirela Stoica (Prince at the time)");
  await expect(line("Loyal")).toContainText("For holding the door");
  await expect(choices.getByRole("listitem", { name: "Harpy" }).getByText("Gives Prominent · Noble · Guardian")).toBeVisible();
  const statusBox = (await status.boundingBox())!;
  const titlesBox = (await titles.boundingBox())!;
  if (p.viewportSize()!.width >= 1024) expect(titlesBox.x).toBeGreaterThanOrEqual(statusBox.x + statusBox.width);
  else expect(titlesBox.y).toBeGreaterThanOrEqual(statusBox.y + statusBox.height);
  expect(await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  // The Prince is held, by one character at a time: not for the taking.
  const princeRow = choices.getByRole("listitem", { name: "Prince", exact: true });
  await expect(princeRow.getByText(/Held by Mirela Stoica: only one holds it at a time/)).toBeVisible();
  await expect(princeRow.getByRole("button", { name: "Take Prince" })).toHaveCount(0);

  // Harpy, the first title, is active at once, and gives its status.
  await choices.getByRole("button", { name: "Take Harpy" }).click();
  await expect(held.getByRole("listitem", { name: "Harpy" }).getByText("active", { exact: true })).toBeVisible();
  for (const name of ["Prominent", "Noble", "Guardian"]) await expect(line(name)).toContainText("from the title Harpy");
  await expect(line("Noble").getByText("abiding", { exact: true })).toBeVisible();
  await p.screenshot(shots("status-titles"));
  // The storytellers are told, with a link to the tab.
  const bell = (await (await lead.page.request.get("/api/notifications")).json()).items as { summary: string; link: string }[];
  expect(bell.find((i) => i.summary === "Lady Vasquez took the title Harpy (Camarilla): +Prominent, +Noble, +Guardian")?.link).toBe(`/characters/${id}/status`);

  // Keeper of Elysium, made active in place of Harpy: its status instead.
  await choices.getByRole("button", { name: "Take Keeper of Elysium" }).click();
  await choices.getByRole("group", { name: "Take Keeper of Elysium" }).getByRole("button", { name: "Make it active" }).click();
  await expect(held.getByRole("listitem", { name: "Keeper of Elysium" }).getByText("active", { exact: true })).toBeVisible();
  await expect(held.getByRole("listitem", { name: "Harpy" }).getByText("not active")).toBeVisible();
  for (const name of ["Enforcer", "Guardian"]) await expect(line(name)).toContainText("from the title Keeper of Elysium");
  await expect(list).not.toContainText("Harpy");

  // Given up, it leaves Harpy held but not active, and no status from either.
  await held.getByRole("button", { name: "Give up Keeper of Elysium" }).click();
  await held.getByRole("button", { name: "Yes, give it up" }).click();
  await expect(held.getByRole("listitem", { name: "Keeper of Elysium" })).toHaveCount(0);
  await expect(titles.getByText("No title is active, so none gives status.")).toBeVisible();
  await expect(list).not.toContainText("from the title");
  await held.getByRole("button", { name: "Make Harpy active" }).click();
  await expect(line("Noble")).toContainText("from the title Harpy");
  // Back on the tab holding a title, the titles to choose wait behind a button.
  await p.reload();
  const another = choices.getByRole("button", { name: /Choose another title/ });
  await expect(another).toHaveAttribute("aria-expanded", "false");
  await expect(choices.getByRole("listitem", { name: "Sheriff" })).toHaveCount(0);
  await expect(line("Loyal")).toBeVisible();
  await p.screenshot(shots("status-titles-held"));
  await another.click();
  await expect(choices.getByRole("listitem", { name: "Sheriff" })).toBeVisible();

  // The bans are below the status; one opens in a panel saying what it does and why.
  const bans = p.locator("section").filter({ has: p.getByRole("heading", { name: "Status bans" }) });
  await bans.getByRole("button", { name: /lesser ban: Not Embraced into a pillar clan/ }).click();
  const panel = p.getByRole("dialog", { name: "Lesser status ban" });
  await expect(panel.getByText("A lesser ban cuts fleeting status to 3, a greater to 1 (MET: VTM p. 312).", { exact: false })).toBeVisible();
  await expect(panel.getByText("It applies: Lady Vasquez's sheet shows it.")).toBeVisible();
  await expect(panel.getByRole("button", { name: /Exempt/ })).toHaveCount(0);
  await panel.getByRole("button", { name: "Close" }).click();
  await expect(panel).toBeHidden();

  // The lead, on a phone: the titles sidebar sits below the status and its bans, and
  // the panel fills the screen, where the lead makes Lady Vasquez exempt with a reason.
  const l = lead.page;
  await l.setViewportSize({ width: 390, height: 844 });
  await l.goto(`/characters/${id}/status`);
  const leadBans = l.locator("section").filter({ has: l.getByRole("heading", { name: "Status bans" }) });
  const leadStatus = l.locator("section").filter({ has: l.getByRole("heading", { name: "Status", exact: true }) });
  const leadTitles = l.getByRole("complementary", { name: "Titles" });
  await expect(leadBans.getByRole("button", { name: /lesser ban: Not Embraced into a pillar clan/ })).toBeVisible();
  await expect(leadTitles.getByRole("listitem", { name: "Harpy" })).toBeVisible();
  const leadStatusBox = (await leadStatus.boundingBox())!;
  const bansBox = (await leadBans.boundingBox())!;
  const leadTitlesBox = (await leadTitles.boundingBox())!;
  expect(bansBox.y).toBeGreaterThan(leadStatusBox.y + leadStatusBox.height - 1);
  expect(leadTitlesBox.y).toBeGreaterThan(bansBox.y + bansBox.height - 1);
  expect(await l.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await l.screenshot(shots("status-titles-lead-phone"));
  await leadBans.getByRole("button", { name: /lesser ban: Not Embraced into a pillar clan/ }).click();
  const leadPanel = l.getByRole("dialog", { name: "Lesser status ban" });
  await expect(leadPanel).toBeVisible();
  const panelBox = (await leadPanel.boundingBox())!;
  expect(Math.round(panelBox.width)).toBe(390);
  expect(Math.round(panelBox.height)).toBe(844);
  await l.screenshot(shots("status-ban-panel-phone"));
  await leadPanel.getByRole("button", { name: "Exempt Lady Vasquez" }).click();
  await leadPanel.getByLabel("Why, for the character's log").fill("Petitioned the Prince");
  await leadPanel.getByRole("button", { name: "Exempt Lady Vasquez" }).click();
  await expect(leadPanel.getByText("Staff made Lady Vasquez exempt: Petitioned the Prince")).toBeVisible();
  await leadPanel.getByRole("button", { name: "Close" }).click();
  await expect(leadPanel).toBeHidden();
  await expect(leadBans.getByRole("button", { name: /lesser ban: Not Embraced into a pillar clan/ })).toContainText("exempt");
});

test("a troupe chooses whether its badges print titles and status: by default all of it, or negative status only", async ({ browser }) => {
  const custodian = await person(browser, "badgeset-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "badgeset-lead");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Ribbons ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  const l = lead.page;
  const send = async (url: string, data: object, method: "POST" | "PUT" = "POST") => {
    const response = await l.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };

  // Two Camarilla NPCs: Prince Ottavio, and Lisette, the Sheriff, Loyal and Warned.
  const npc = async (name: string, title: string) => {
    const { id } = await send(`/api/troupes/${troupeId}/npcs`, { name, wizard: false });
    await send(`/api/characters/${id}/npc/ratings`, { category: "sect", name: "Camarilla", rating: null, detail: "" }, "PUT");
    await send(`/api/troupes/${troupeId}/characters/${id}/titles`, { titles: [title] }, "PUT");
    return id as string;
  };
  const prince = await npc("Prince Ottavio", "Prince");
  const lisette = await npc("Lisette Marchand", "Sheriff");
  for (const name of ["Loyal", "Warned"]) await send(`/api/characters/${lisette}/status`, { name, patron_text: "Prince Ottavio" });

  // By default, a badge prints the titles held here and the status carried into a game, negative status marked out.
  await l.goto(`/print/troupes/${troupeId}/badges?characters=${prince},${lisette}`);
  let ottavio = l.getByRole("article", { name: "Badge for Prince Ottavio" });
  let warned = l.getByRole("article", { name: "Badge for Lisette Marchand" });
  await expect(ottavio.getByText("Prince", { exact: true })).toBeVisible();
  await expect(ottavio.getByText("Status: Authority, Commander, Sovereign")).toBeVisible();
  await expect(warned.getByText("Sheriff", { exact: true })).toBeVisible();
  await expect(warned.getByText(/^Status: .*Loyal, Warned$/)).toBeVisible();
  await expect(warned.getByLabel("Negative status: Warned")).toBeVisible();
  await l.screenshot(shots("badges-status"));

  // On About, the lead turns titles off and prints negative status only.
  await l.goto(`/troupes/${troupeId}`);
  const setting = l.locator("section").filter({ has: l.getByRole("heading", { name: "Badges", exact: true }) });
  await expect(setting.getByLabel("Print titles")).toBeChecked();
  await expect(setting.getByLabel(/^All/)).toBeChecked();
  // Each saves as it is clicked, and shows once saved.
  await setting.getByLabel("Print titles").click();
  await expect(setting.getByLabel("Print titles")).not.toBeChecked();
  await setting.getByLabel(/^Negative only/).click();
  await expect(setting.getByLabel(/^Negative only/)).toBeChecked();
  await l.screenshot(shots("badge-setting"));

  // Now Lisette's badge shows her Warned and nothing else from either section; the Prince's, neither.
  await l.goto(`/print/troupes/${troupeId}/badges?characters=${prince},${lisette}`);
  ottavio = l.getByRole("article", { name: "Badge for Prince Ottavio" });
  warned = l.getByRole("article", { name: "Badge for Lisette Marchand" });
  await expect(warned.getByText("Status: Warned", { exact: true })).toBeVisible();
  await expect(warned.getByLabel("Negative status: Warned")).toBeVisible();
  await expect(warned.getByText("Sheriff", { exact: true })).toHaveCount(0);
  await expect(warned.getByText(/Loyal/)).toHaveCount(0);
  await expect(ottavio.getByText("Neonate", { exact: true })).toBeVisible();
  await expect(ottavio.getByText("Prince", { exact: true })).toHaveCount(0);
  await expect(ottavio.getByText(/^Status:/)).toHaveCount(0);
});

test("at a game, a Seneschal elder chooses one source of status, spends Authority and Loyal with Undo, and adds Courageous from the Prince", async ({ browser }) => {
  const custodian = await person(browser, "gstatus-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "gstatus-lead");
  const player = await person(browser, "gstatus-player");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Choices ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;
  const send = async (page: Page, method: "POST" | "PUT" | "GET", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };

  // Isadora, a Camarilla Brujah, built through the API and accepted home.
  const p = player.page;
  const { id } = await send(p, "POST", "/api/characters", { splat: "vampire", name: "Isadora" });
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
  const build: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Generation", 3], ["Fame", 2], ["Herd", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, picks] of Object.entries(build))
    await send(p, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send(p, "POST", `/api/characters/${id}/creation/complete`, {});
  const asked = await send(p, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});

  // The court: an NPC Prince, and Isadora, an elder, is Seneschal and Primogen; the
  // Seneschal, the higher, is her active title. She holds Loyal.
  const prince = await send(lead.page, "POST", `/api/troupes/${troupeId}/npcs`, { name: "Prince Varga", wizard: false });
  await send(lead.page, "PUT", `/api/characters/${prince.id}/npc/ratings`, { category: "sect", name: "Camarilla", rating: null, detail: "" });
  await send(lead.page, "PUT", `/api/troupes/${troupeId}/characters/${prince.id}/titles`, { titles: ["Prince"] });
  await send(lead.page, "PUT", `/api/troupes/${troupeId}/characters/${id}/titles`, { titles: ["Seneschal", "Primogen"] });
  await send(p, "POST", `/api/characters/${id}/status`, { name: "Loyal", patron_text: "The Keeper of Elysium" });

  // The Status tab: one source of abiding status to choose for the game.
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Status" }).click();
  await expect(p.getByText("Acknowledged by the Camarilla")).toBeVisible();
  await expect(p.getByText("Choose your one source of abiding status for this game")).toBeVisible();
  await expect(p.getByRole("heading", { name: "Abiding status" })).toHaveCount(0);
  await p.screenshot(shots("play-status-choose"));
  await p.getByRole("button", { name: "Choose Seneschal" }).click();
  const abiding = p.locator("section").filter({ has: p.getByRole("heading", { name: "Abiding status" }) });
  await expect(abiding.getByText("Noble", { exact: true })).toBeVisible();
  await expect(abiding.getByText("Authority", { exact: true })).toHaveCount(0);
  await expect(p.getByText("Your choices are locked for this game; staff can change them.")).toBeVisible();
  await expect(p.getByRole("button", { name: "Choose Primogen" })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Change" })).toHaveCount(0);

  // The Prince is away tonight: the Seneschal holds Authority.
  await p.getByRole("button", { name: "The Prince is absent" }).click();
  await expect(p.getByText("The Prince is absent: Authority")).toBeVisible();
  await expect(abiding.getByText("Authority", { exact: true })).toBeVisible();

  // Spending Authority greys it out for the game; Undo gives it back.
  await abiding.getByRole("button", { name: "Spend Authority" }).click();
  await p.getByRole("dialog", { name: "Note for this spend" }).getByRole("button", { name: "Save" }).click();
  await expect(abiding.getByRole("button", { name: "Undo spending Authority" })).toBeVisible();
  await expect(abiding.getByText("Spent", { exact: true })).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await abiding.getByRole("button", { name: "Undo spending Authority" }).click();
  await expect(abiding.getByRole("button", { name: "Spend Authority" })).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // Spending Loyal takes it off the sheet for good; Undo puts it back.
  const fleeting = p.locator("section").filter({ has: p.getByRole("heading", { name: "Fleeting status" }) });
  await fleeting.getByRole("button", { name: "Spend Loyal" }).click();
  const note = p.getByRole("dialog", { name: "Note for this spend" });
  await note.getByLabel("What was Loyal for? (optional)").fill("a car from the motor pool");
  await note.getByRole("button", { name: "Save" }).click();
  await expect(fleeting.getByText("Spent for good")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  expect((await send(p, "GET", `/api/characters/${id}/status`)).held).toEqual([]);
  await p.screenshot(shots("play-status-spent"));
  await fleeting.getByRole("button", { name: "Undo spending Loyal" }).click();
  await expect(fleeting.getByRole("button", { name: "Spend Loyal" })).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  expect((await send(p, "GET", `/api/characters/${id}/status`)).held.map((h: { name: string }) => h.name)).toEqual(["Loyal"]);

  // Courageous, from the Prince, added at the game.
  await p.getByRole("button", { name: "Add status" }).click();
  const form = p.getByRole("form", { name: "Add status" });
  await form.getByLabel("Status").selectOption("Courageous");
  await form.getByRole("combobox", { name: "A character" }).fill("varga");
  await p.getByRole("listbox", { name: "Patrons" }).getByRole("option", { name: /Prince Varga/ }).click();
  await form.getByRole("button", { name: "Add status" }).click();
  await expect(fleeting.getByText("Courageous", { exact: true })).toBeVisible();
  await p.screenshot(shots("play-status-added"));

  // The Status tab and the log show it, given at this game.
  await p.goto(`/characters/${id}/status`);
  const card = p.locator("section").filter({ has: p.getByRole("heading", { name: "Status", exact: true }) });
  await expect(card.getByText("from Prince Varga (Prince at the time)")).toBeVisible();
  await p.getByRole("link", { name: "Log", exact: true }).click();
  await expect(p.getByText("gstatus-player gave Isadora the fleeting status Courageous, from Prince Varga (Prince at the time) at game 1.")).toBeVisible();
  await expect(p.getByText("gstatus-player spent Isadora's Loyal (from The Keeper of Elysium) (a car from the motor pool).")).toBeVisible();
  await expect(p.getByText("gstatus-player undid spending Isadora's Loyal (from The Keeper of Elysium): it is back.")).toBeVisible();

  // The lead, from the game's Play View, can change the locked choice.
  const l = lead.page;
  await l.goto(`/play/characters/${id}?tab=status`);
  await l.getByRole("button", { name: "Change" }).click();
  await expect(l.getByRole("button", { name: "Choose Primogen" })).toHaveCount(0);
  await l.getByRole("button", { name: "Choose Elder" }).click();
  await expect(l.getByText("Abiding status from Elder, chosen for this game.")).toBeVisible();
});

test("at a game, a Camarilla character with Leadership 2 learns about two of a rival's status, and a Sabbat character sees none", async ({ browser }) => {
  const custodian = await person(browser, "rival-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "rival-lead");
  const player = await person(browser, "rival-player");
  const rival = await person(browser, "rival-elena");
  const sabbat = await person(browser, "rival-sabbat");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Rivals ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  await backstoryOptional(custodian.page, (await made.json()).id);
  const troupeId = (await made.json()).id;
  const send = async (page: Page, method: "POST" | "PUT" | "GET", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  // A Brujah of `sect`, built through the API and accepted home.
  const build = async (page: Page, name: string, sect: string, leadership: number): Promise<string> => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: sect, rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 3 - leadership], ["Firearms", 2], ["Investigation", 1], ["Leadership", leadership], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
      disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
    };
    for (const [category, chosen] of Object.entries(picks))
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: chosen.map(([name, rating]) => ({ name, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`, {});
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});
    return id;
  };

  // Marguerite has Leadership 2. Her rival Elena Moretti holds three fleeting status
  // and a Warned, and has spent Honorable tonight. Brother Ash is of the Sabbat.
  const marguerite = await build(player.page, "Marguerite", "Camarilla", 2);
  const elena = await build(rival.page, "Elena Moretti", "Camarilla", 1);
  const ash = await build(sabbat.page, "Brother Ash", "Sabbat", 1);
  for (const [name, patron, story] of [
    ["Loyal", "Prince Varga", "For holding the door"],
    ["Courageous", "Keeper Ines", "For facing the Sheriff"],
    ["Honorable", "Seneschal Roth", "For keeping her word"],
    ["Warned", "Sheriff Hale", "For the brawl at the docks"],
  ])
    await send(rival.page, "POST", `/api/characters/${elena}/status`, { name, patron_text: patron, place: "Elysium", story });
  const honorable = (await send(rival.page, "GET", `/api/characters/${elena}/status`)).held.find((h: { name: string }) => h.name === "Honorable").id;
  const spend = { id: crypto.randomUUID(), happened_at: new Date().toISOString(), kind: "change", tracker: `held:${honorable}`, amount: -1 };
  await send(rival.page, "POST", `/api/characters/${elena}/play/taps`, { taps: [spend] });

  // Leadership's two uses are under Uses this game.
  const p = player.page;
  await p.goto(`/play/characters/${marguerite}?tab=tracker`);
  const uses = p.locator("section").filter({ has: p.getByRole("heading", { name: "Uses this game" }) });
  await expect(uses.getByText("Leadership", { exact: true })).toBeVisible();
  await expect(uses.getByText("Skills · 2 of 2 left")).toBeVisible();

  // On the Status tab, Marguerite finds Elena and knows her status, but not where it came from.
  await p.getByRole("tab", { name: "Status" }).click();
  const others = p.locator("section").filter({ has: p.getByRole("heading", { name: "Others at this game" }) });
  await others.getByLabel("Find a character").fill("moretti");
  await others.getByRole("button", { name: /Elena Moretti/ }).click();
  await expect(others.getByText("Acknowledged by the Camarilla")).toBeVisible();
  for (const name of ["Warned", "Loyal", "Courageous", "Honorable"]) await expect(others.getByText(name, { exact: true })).toBeVisible();
  await expect(others.getByText("spent", { exact: true })).toBeVisible();
  // Negative status is public, its patron and all.
  await expect(others.getByText("From Sheriff Hale, at Elysium")).toBeVisible();
  await expect(others.getByText("Prince Varga")).toHaveCount(0);
  await expect(others.getByText("Leadership: 2 of 2 left this game", { exact: false })).toBeVisible();

  // Learning about Loyal and Courageous uses both of her Leadership.
  await others.getByRole("button", { name: "Learn about Loyal" }).click();
  await expect(others.getByText("From Prince Varga, at Elysium")).toBeVisible();
  await expect(others.getByText("For holding the door")).toBeVisible();
  await expect(others.getByText("Leadership: 1 of 2 left this game", { exact: false })).toBeVisible();
  await others.getByRole("button", { name: "Learn about Courageous" }).click();
  await expect(others.getByText("For facing the Sheriff")).toBeVisible();
  await expect(others.getByText("Leadership: 0 of 2 left this game", { exact: false })).toBeVisible();
  await p.screenshot(shots("play-others-learned"));

  // A third is refused: the button is off, and the API says no.
  await expect(others.getByRole("button", { name: "Learn about Honorable" })).toBeDisabled();
  const looked = await send(p, "GET", `/api/characters/${marguerite}/play/others/${elena}`);
  const key = looked.status.find((s: { name: string }) => s.name === "Honorable").key;
  const refused = await p.request.post(`/api/characters/${marguerite}/play/others/${elena}/learn`, { headers, data: { id: crypto.randomUUID(), key } });
  expect(refused.status()).toBe(409);
  await expect(others.getByText("For keeping her word")).toHaveCount(0);

  // Undo gives a use back, and what it learned is forgotten.
  await others.getByRole("button", { name: "Undo learning about Loyal" }).click();
  await expect(others.getByText("For holding the door")).toHaveCount(0);
  await expect(others.getByText("Leadership: 1 of 2 left this game", { exact: false })).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await expect(others.getByRole("button", { name: "Learn about Loyal" })).toBeEnabled();
  await p.getByRole("tab", { name: "Tracker" }).click();
  await expect(uses.getByText("Skills · 1 of 2 left")).toBeVisible();
  // The log replays without the undone tap.
  await expect(p.getByText("Learned about Elena Moretti's Courageous: Leadership 2 → 1")).toBeVisible();
  await expect(p.getByText("Undid: Learned about Elena Moretti's Loyal: Leadership 2 → 1")).toBeVisible();

  // Brother Ash, of the Sabbat, sees Elena's name and sect, and none of her status.
  const s = sabbat.page;
  await s.goto(`/play/characters/${ash}?tab=status`);
  const theirs = s.locator("section").filter({ has: s.getByRole("heading", { name: "Others at this game" }) });
  await theirs.getByRole("button", { name: /Elena Moretti/ }).click();
  await expect(theirs.getByText("Only the Camarilla’s own know their status.")).toBeVisible();
  for (const name of ["Warned", "Loyal", "Courageous", "Sheriff Hale"]) await expect(theirs.getByText(name)).toHaveCount(0);
  await s.screenshot(shots("play-others-sabbat"));
});

test("titles by sect: a Camarilla troupe gives Camarilla titles only to its own, and a house title gives status", async ({ browser }) => {
  const custodian = await person(browser, "sects-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "sects-lead");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Elysium ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  const p = lead.page;
  const limited = await p.request.patch(`/api/troupes/${troupeId}`, { headers, data: { allowed_sects: ["Camarilla"] } });
  expect(limited.status(), await limited.text()).toBe(200);
  const npc = async (name: string, sect: string) => {
    const response = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(response.status(), await response.text()).toBe(201);
    const id = (await response.json()).id;
    const rated = await p.request.put(`/api/characters/${id}/npc/ratings`, { headers, data: { category: "sect", name: sect, rating: null } });
    expect(rated.status(), await rated.text()).toBe(200);
    return id as string;
  };
  await npc("Elena Varga", "Camarilla");
  const tomas = await npc("Tomas Reyes", "Anarch");

  // The Titles tab: the Camarilla's titles and those of any sect, with the status each gives.
  await p.goto(`/troupes/${troupeId}/titles`);
  await expect(p.getByRole("heading", { name: "Camarilla titles" })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Titles of any sect" })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Sabbat titles" })).toHaveCount(0);
  await expect(p.getByRole("listitem", { name: "Prince", exact: true }).getByText("Gives Authority · Commander · Sovereign")).toBeVisible();

  // A house title of the Camarilla, giving Guardian.
  const adding = p.locator("section").filter({ has: p.getByRole("heading", { name: "Add a title" }) });
  await adding.getByLabel("Name").fill("Master of Elysium");
  await adding.getByLabel("Sect").selectOption("Camarilla");
  await adding.getByLabel("Guardian").check();
  await adding.getByRole("button", { name: "Add", exact: true }).click();
  const master = p.getByRole("listitem", { name: "Master of Elysium" });
  await expect(master.getByText("Gives Guardian")).toBeVisible();
  await expect(master.getByText("ours")).toBeVisible();
  await expect(master.getByText("No one")).toBeVisible();

  // The picker offers each character the titles of its sect and of any sect.
  await p.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await p.getByRole("button", { name: "Give Elena Varga a title" }).click();
  const dialog = p.getByRole("dialog");
  await expect(dialog.getByText("Elena Varga is Camarilla: Camarilla titles and those of any sect.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Prince", exact: true })).toBeVisible();
  await p.screenshot(shots("give-title-by-sect"));
  await dialog.getByRole("button", { name: "Master of Elysium", exact: true }).click();
  await expect(p.getByRole("button", { name: "Take the title Master of Elysium from Elena Varga" })).toBeVisible();
  await p.getByRole("button", { name: "Give Tomas Reyes a title" }).click();
  await expect(dialog.getByText("Tomas Reyes is Anarch: Anarch titles and those of any sect.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Prince", exact: true })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Close" }).click();
  // And the API refuses Prince to an Anarch.
  const refused = await p.request.put(`/api/troupes/${troupeId}/characters/${tomas}/titles`, { headers, data: { titles: ["Prince"] } });
  expect(refused.status()).toBe(409);
  expect((await refused.json()).detail).toBe("Prince is a Camarilla title, and Tomas Reyes is Anarch.");

  // Who holds what; and changing what the house title gives changes it for its holders.
  await p.goto(`/troupes/${troupeId}/titles`);
  await expect(master.getByRole("link", { name: "Elena Varga" })).toBeVisible();
  await master.getByRole("button", { name: "Change the title Master of Elysium" }).click();
  await dialog.getByLabel("Prominent").check();
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(master.getByText("Gives Guardian · Prominent")).toBeVisible();
  await p.screenshot(shots("titles-by-sect"));
});
