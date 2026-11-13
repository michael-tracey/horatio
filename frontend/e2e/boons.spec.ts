import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, person, makeCustodian, builtVampire, ATTRIBUTES_AND_FOCUSES, backstoryOptional, shots } from "./support";

/** Boons: the troupe's ledger, for its running staff: registering a game's boons at once, settling, editing and trading them, each with its own log; the boon standings; the Play View's Boons tab, where players report boons and see what the troupe lets them (#686); review, where reports wait for staff to accept them (#687); the Harpy keeping the ledger as their character (#688); and Lesser Harpies the Harpy gives access (#689). */

closeContextsAfterEach();

test("staff keep the boon ledger: a game's boons at once, then a settling, an edit and a trade, each in its log", async ({ browser }) => {
  const custodian = await person(browser, "boons-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "boons-lead");
  const player = await person(browser, "boons-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Ledger of Debts ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const mireille = await builtVampire(player.page, "Mireille Dauvin", "Brujah", build);
  const asked = await send(player.page, "POST", `/api/characters/${mireille}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Anselm Roque" });

  // The ledger is off by default. The lead switches it on in the troupe's settings.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/settings`);
  const keep = l.getByRole("checkbox", { name: /^Keep a boon ledger/ });
  await expect(keep).not.toBeChecked();
  await keep.click();
  await expect(l.getByText(/^The boon ledger is on\./)).toBeVisible();
  await expect(keep).toBeChecked();

  // Under Characters, the Boons screen: register a game's boons at once.
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: "Boons", exact: true }).click();
  await expect(l.getByText("No open boons yet.")).toBeVisible();
  await l.getByRole("button", { name: "Register boons" }).click();
  const entry = l.getByRole("form", { name: "Register boons" });
  await entry.getByLabel("Date for new rows").fill("2026-10-03");
  await entry.getByLabel("Where they come from (optional)").fill("Elysium, 3 October");
  const pick = async (row: ReturnType<Page["getByRole"]>, side: "Debtor" | "Creditor", typed: string, option: RegExp) => {
    await row.getByRole("combobox", { name: side }).fill(typed);
    await row.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: option }).click();
  };
  const first = entry.getByRole("listitem", { name: "Boon 1" });
  await pick(first, "Debtor", "Mireille", /Mireille Dauvin/);
  await pick(first, "Creditor", "Anselm", /Anselm Roque/);
  await first.getByLabel("How many").fill("3");
  await first.getByLabel("Reason").fill("Secret");
  await entry.getByRole("button", { name: "Add a row" }).click();
  const second = entry.getByRole("listitem", { name: "Boon 2" });
  await pick(second, "Debtor", "Elder Varga", /name only/);
  await pick(second, "Creditor", "Mireille", /Mireille Dauvin/);
  await second.getByLabel("Kind").selectOption("trivial");
  await second.getByLabel("Reason").fill("Introduction");
  await entry.getByRole("button", { name: "Register 4 boons" }).click();
  await expect(l.getByText("Registered 4 boons.")).toBeVisible();

  const boons = l.getByRole("list", { name: "Boons" });
  await expect(boons.getByRole("listitem", { name: "Mireille Dauvin owes Anselm Roque, minor" })).toHaveCount(3);
  await expect(l.getByRole("tab", { name: /^Open/ })).toContainText("(4)");

  // One of the three is called in: it leaves the open boons for the settled.
  const owed = boons.getByRole("listitem", { name: "Mireille Dauvin owes Anselm Roque, minor" }).first();
  await owed.getByRole("button", { name: "Open" }).click();
  await owed.getByRole("button", { name: "Settle" }).click();
  const settle = owed.getByRole("form", { name: "Settle: Mireille Dauvin owes Anselm Roque" });
  await settle.getByLabel(/^Called in/).check();
  await settle.getByLabel("Note (optional)").fill("Called in for a favour at court");
  await settle.getByRole("button", { name: "Settle it" }).click();
  await expect(l.getByRole("tab", { name: /^Open/ })).toContainText("(3)");
  await l.getByRole("tab", { name: /^Settled/ }).click();
  await expect(boons.getByRole("listitem")).toHaveCount(1);
  const settled = boons.getByRole("listitem", { name: "Mireille Dauvin owes Anselm Roque, minor" });
  await expect(settled).toContainText("Settled: called in");
  await settled.getByRole("button", { name: "Open" }).click();
  const settledLog = settled.getByRole("list", { name: "Log of Mireille Dauvin owes Anselm Roque" });
  await expect(settledLog).toContainText("Elysium, 3 October");
  await expect(settledLog).toContainText("Called in for a favour at court");

  // The trivial boon was typed in wrong: an edit, with why, keeps what changed in its log.
  await l.getByRole("tab", { name: /^Open/ }).click();
  await expect(boons.getByRole("listitem")).toHaveCount(3);
  const varga = boons.getByRole("listitem", { name: "Elder Varga owes Mireille Dauvin, trivial" });
  await varga.getByRole("button", { name: "Open" }).click();
  await varga.getByRole("button", { name: "Edit" }).click();
  const edit = varga.getByRole("form", { name: "Edit: Elder Varga owes Mireille Dauvin" });
  await edit.getByLabel("Kind").selectOption("minor");
  await edit.getByLabel("Why the edit").fill("Typed in wrong");
  await edit.getByRole("button", { name: "Save the edit" }).click();
  const edited = boons.getByRole("listitem", { name: "Elder Varga owes Mireille Dauvin, minor" });
  await expect(edited.getByRole("list", { name: "Log of Elder Varga owes Mireille Dauvin" })).toContainText("Kind: Trivial → Minor");

  // Anselm trades one of his to Elder Varga: the boon keeps its history.
  const held = boons.getByRole("listitem", { name: "Mireille Dauvin owes Anselm Roque, minor" }).first();
  await held.getByRole("button", { name: "Open" }).click();
  await held.getByRole("button", { name: "Trade" }).click();
  const trade = held.getByRole("form", { name: "Trade: Mireille Dauvin owes Anselm Roque" });
  await trade.getByRole("combobox", { name: "Traded to" }).fill("Elder Varga");
  await trade.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /name only/ }).click();
  await trade.getByRole("button", { name: "Record the trade" }).click();
  const traded = boons.getByRole("listitem", { name: "Mireille Dauvin owes Elder Varga, minor" });
  await expect(traded.getByRole("list", { name: "Log of Mireille Dauvin owes Elder Varga" })).toContainText("Creditor: Anselm Roque → Elder Varga");

  // On Mireille's sheet, staff see what she owes and is owed, with a way into the ledger.
  await l.goto(`/characters/${mireille}`);
  const card = l.getByRole("listitem", { name: `Boons in Ledger of Debts ${run}` });
  await expect(card).toContainText("Owes: 2 minor");
  await expect(card).toContainText("Is owed: 1 minor");
  await card.getByRole("link", { name: "In the boon ledger" }).click();
  await expect(l.getByRole("list", { name: "Boons" }).getByRole("listitem")).toHaveCount(3);

  // Her player isn't shown her boons (that comes with #686), and can't open the ledger.
  const p = player.page;
  const mine = await p.request.get(`/api/characters/${mireille}/boons`);
  expect((await mine.json()).troupes).toEqual([]);
  const refused = await p.request.get(`/api/troupes/${troupe.id}/boons`);
  expect(refused.status()).toBe(403);
});

test("staff see the boon standings: each character's net by the troupe's weights, which they can change", async ({ browser }) => {
  const custodian = await person(browser, "bstand-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bstand-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Standing of Debts ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  const isolde = await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Isolde Fenwright" });
  const casimir = await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Casimir Wode" });
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  const owes = (debtor: string, creditor: string, kind: string) => ({ debtor: { character_id: debtor }, creditor: { character_id: creditor }, kind, made_on: "2026-10-03" });
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, { boons: [owes(isolde.id, casimir.id, "major"), owes(casimir.id, isolde.id, "minor")] });

  // Under Characters, Boon standings: Casimir is owed a major and owes a minor.
  await l.goto(`/troupes/${troupe.id}`);
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: "Boon standings", exact: true }).click();
  const standing = l.getByRole("table", { name: "Standing by character" });
  await expect(standing.getByRole("row", { name: /Casimir Wode/ })).toContainText("+2");
  await expect(standing.getByRole("row", { name: /Isolde Fenwright/ })).toContainText("−2");
  await expect(l.getByRole("table", { name: "Owing each other" })).toContainText("Isolde Fenwright");

  // The troupe weighs a major boon at 4: the sums follow.
  await l.getByRole("button", { name: "Change" }).click();
  await l.getByLabel("Major").fill("4");
  await l.getByRole("button", { name: "Save weights" }).click();
  await expect(l.getByText("The boon weights are saved.")).toBeVisible();
  await expect(standing.getByRole("row", { name: /Casimir Wode/ })).toContainText("+3");
  await expect(l.getByText(/Major 4/)).toBeVisible();
});

test("a Disgraced creditor's boons need not be repaid, and staff register the boon an apology owes for a slip (#694)", async ({ browser }) => {
  const custodian = await person(browser, "bslip-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bslip-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Slips and Debts ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  const camarilla = async (name: string) => {
    const npc = await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, { name, wizard: false });
    await send(l, "PUT", `/api/characters/${npc.id}/npc/ratings`, { category: "sect", name: "Camarilla", rating: null, detail: "" });
    return npc.id as string;
  };
  const corvin = await camarilla("Corvin Ashgrave");
  const maelis = await camarilla("Maelis Thorne");
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [{ debtor: { character_id: maelis }, creditor: { character_id: corvin }, kind: "minor", made_on: "2026-10-03", reason: "Safe passage" }],
  });
  await send(l, "POST", `/api/characters/${corvin}/status`, { name: "Disgraced", patron_text: "Prince Aurelian", reason: "Broke the Masquerade" });

  // The ledger says Maelis's boon to Corvin need not be repaid while he is Disgraced.
  await l.goto(`/troupes/${troupe.id}/boons`);
  const boons = l.getByRole("list", { name: "Boons" });
  await expect(boons.getByRole("listitem", { name: "Maelis Thorne owes Corvin Ashgrave, minor" })).toContainText(
    "Need not be repaid while Corvin Ashgrave is Disgraced (p. 316).",
  );

  // On Corvin's status, staff register the major boon his apology owes the Prince.
  await l.goto(`/characters/${corvin}/status`);
  const card = l.locator("section").filter({ has: l.getByRole("heading", { name: "Status", exact: true }) });
  await card.getByRole("listitem", { name: "Disgraced" }).getByRole("button", { name: "Apology boon…" }).click();
  const form = card.getByRole("form", { name: "Apology boon for a slip while Disgraced" });
  await expect(form.getByLabel("Owed to: whoever was wronged")).toHaveValue("Prince Aurelian");
  await form.getByRole("button", { name: "Register a major boon" }).click();
  await expect(l.getByText("Registered a major boon owed by Corvin Ashgrave.")).toBeVisible();
  await l.goto(`/troupes/${troupe.id}/boons`);
  await expect(boons.getByRole("listitem", { name: "Corvin Ashgrave owes Prince Aurelian, major" })).toContainText("An apology for a slip while Disgraced");
});

test("staff see the boon statistics: the ledger over time, who owes whom, between clans and at each game", async ({ browser }) => {
  const custodian = await person(browser, "bstats-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bstats-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Debts Charted ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  const wendeline = await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Wendeline Krause" });
  const thaddeus = await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Thaddeus Grue" });
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  const owes = (debtor: object, creditor: object, kind: string) => ({ debtor, creditor, kind, made_on: "2026-10-03" });
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [owes({ character_id: wendeline.id }, { character_id: thaddeus.id }, "major"), owes({ name: "The Grey Countess" }, { character_id: wendeline.id }, "minor")],
  });

  // Under Characters, Boon statistics: each of the four charts, every one with its table.
  await l.goto(`/troupes/${troupe.id}`);
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: "Boon statistics", exact: true }).click();
  for (const title of ["Boons registered", "Who owes whom", "Debt between clans", "Boons at each game"]) {
    await expect(l.getByRole("figure", { name: title })).toBeVisible();
  }
  // Open debt over time by weight, read as a table: the major (3) and the minor (1) stand this month.
  await l.getByRole("radio", { name: "Open debt" }).click();
  await l.getByRole("radio", { name: "Weight" }).click();
  const overTime = l.getByRole("figure", { name: "Open debt over time" });
  await overTime.getByRole("button", { name: "Show as table" }).click();
  await expect(overTime.getByRole("table").getByRole("row").last().getByRole("cell").last()).toHaveText("4");

  // The network shows both debts, and filtering to the name-only party keeps only hers.
  const web = l.getByRole("figure", { name: "Who owes whom" });
  await expect(web.getByRole("img", { name: /Thaddeus Grue/ })).toBeVisible();
  await expect(web.getByText(/2 of 2 debts shown/)).toBeVisible();
  await l.getByRole("combobox", { name: "Clan", exact: true }).selectOption("Name only");
  await expect(web.getByText(/1 of 2 debts shown/)).toBeVisible();
  await expect(web.getByRole("img", { name: /Thaddeus Grue/ })).toHaveCount(0);
  await expect(web.getByRole("img", { name: /The Grey Countess/ })).toBeVisible();
});

test("in the Play View's Boons tab a player reports a boon, sees what the troupe lets them, and only the creditor's player settles it (#686)", async ({ browser }) => {
  const custodian = await person(browser, "boontab-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "boontab-lead");
  const creditor = await person(browser, "boontab-creditor");
  const debtor = await person(browser, "boontab-debtor");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Debts Told ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const isolde = await home(creditor.page, "Isolde Marrow");
  const tobiah = await home(debtor.page, "Tobiah Venn");
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });

  // By default a player sees only the form: Isolde's player reports that Tobiah owes her.
  const c = creditor.page;
  await c.goto(`/play/characters/${isolde}?tab=boons`);
  const tab = c.getByRole("region", { name: "Boons" });
  const report = tab.getByRole("form", { name: "Report a boon" });
  await expect(report).toBeVisible();
  await expect(tab.getByRole("region", { name: "Owed to Isolde Marrow" })).toHaveCount(0);
  await report.getByLabel("They owe Isolde Marrow").check();
  await report.getByLabel("Who").selectOption({ label: "Tobiah Venn" });
  await report.getByLabel("Kind").selectOption("major");
  await report.getByLabel("Reason").fill("Shelter before dawn");
  await report.getByRole("button", { name: "Report the boon" }).click();
  await expect(c.getByText(`Reported to Debts Told ${run}'s ledger: Tobiah Venn owes Isolde Marrow a major boon.`)).toBeVisible();

  // The lead lets players see what they owe and are owed, and creditors settle.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/settings`);
  await l.getByRole("radio", { name: /^Also what they're owed/ }).check();
  await expect(l.getByText("Saved what players see of the boon ledger.")).toBeVisible();
  await l.getByRole("checkbox", { name: /^Players mark boons owed to them settled/ }).check();
  await expect(l.getByRole("checkbox", { name: /^Players mark boons owed to them settled/ })).toBeChecked();

  // Tobiah's player sees what he owes, with no way to settle it.
  const d = debtor.page;
  await d.goto(`/play/characters/${tobiah}?tab=boons`);
  const owes = d.getByRole("region", { name: "Tobiah Venn owes" });
  const debt = owes.getByRole("listitem", { name: "Major boon to Isolde Marrow" });
  await expect(debt).toContainText("Shelter before dawn");
  await expect(debt.getByRole("button", { name: "Settle" })).toHaveCount(0);

  // Isolde's player sees it owed to her, and forgives it.
  await c.reload();
  const owed = c.getByRole("region", { name: "Owed to Isolde Marrow" });
  const held = owed.getByRole("listitem", { name: "Major boon from Tobiah Venn" });
  await expect(held).toBeVisible();
  await c.screenshot(shots("play-boons"));
  await held.getByRole("button", { name: "Settle" }).click();
  const settle = held.getByRole("form", { name: "Settle the boon" });
  await settle.getByLabel(/^Forgiven/).check();
  await settle.getByLabel("Note (optional)").fill("For old times");
  await settle.getByRole("button", { name: "Mark it settled" }).click();
  await expect(owed.getByText("No boons in the ledger are owed to Isolde Marrow.")).toBeVisible();
  await owed.getByText("Settled (1)").click();
  await expect(owed.getByRole("listitem", { name: "Major boon from Tobiah Venn" })).toContainText("Settled: forgiven");

  // In the ledger, staff see it was done as Isolde.
  await l.goto(`/troupes/${troupe.id}/boons`);
  await l.getByRole("tab", { name: /^Settled/ }).click();
  const row = l.getByRole("list", { name: "Boons" }).getByRole("listitem", { name: "Tobiah Venn owes Isolde Marrow, major" });
  await row.getByRole("button", { name: "Open" }).click();
  const log = row.getByRole("list", { name: "Log of Tobiah Venn owes Isolde Marrow" });
  await expect(log).toContainText("as Isolde Marrow");
  await expect(log).toContainText("For old times");
});

test("held for review, a player's report waits, flagged for its unlinked name, until staff accept it (#687)", async ({ browser }) => {
  const custodian = await person(browser, "brev-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "brev-lead");
  const player = await person(browser, "brev-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Debts Weighed ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const corvin = await builtVampire(player.page, "Corvin Ashby", "Brujah", build);
  const asked = await send(player.page, "POST", `/api/characters/${corvin}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });

  // The lead holds reports for review.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/settings`);
  const hold = l.getByRole("checkbox", { name: /^Boons players report wait for review/ });
  await hold.check();
  await expect(l.getByText("Boons players report now wait for review.")).toBeVisible();
  await expect(hold).toBeChecked();

  // Corvin's player reports that someone not on the list owes him.
  const p = player.page;
  await p.goto(`/play/characters/${corvin}?tab=boons`);
  const tab = p.getByRole("region", { name: "Boons" });
  const report = tab.getByRole("form", { name: "Report a boon" });
  await report.getByLabel("They owe Corvin Ashby").check();
  await report.getByLabel("Who").selectOption({ label: "Someone else…" });
  await report.getByLabel("Their name").fill("Mysterious Stranger");
  await report.getByLabel("Reason").fill("A ride across the river");
  await report.getByRole("button", { name: "Report the boon" }).click();
  await expect(p.getByText(`Sent to Debts Weighed ${run}'s staff for review: Mysterious Stranger owes Corvin Ashby a minor boon.`)).toBeVisible();
  const reports = tab.getByRole("list", { name: "Your reports" });
  await expect(reports).toContainText("Mysterious Stranger owes Corvin Ashby a minor boon");
  await expect(reports).toContainText(`Waiting for Debts Weighed ${run}'s staff to review it.`);

  // The lead sees it waiting, flagged for its name, and accepts it.
  await l.goto(`/troupes/${troupe.id}/boons`);
  await l.getByRole("tab", { name: /^To review/ }).click();
  const row = l.getByRole("list", { name: "Boons to review" }).getByRole("listitem", { name: "To review: Mysterious Stranger owes Corvin Ashby, minor" });
  await expect(row).toContainText("Name not linked (debtor, Mysterious Stranger): No character in the troupe has this name.");
  await expect(row.getByText("Waits for review").first()).toBeVisible();
  await row.getByRole("button", { name: "Review" }).click();
  await row.getByRole("button", { name: "Accept", exact: true }).click();
  const accept = row.getByRole("form", { name: "Accept: Mysterious Stranger owes Corvin Ashby" });
  await accept.getByLabel("Note (optional)").fill("Confirmed with the Harpy");
  await accept.getByRole("button", { name: "Accept it" }).click();
  await expect(l.getByText("Accepted: Mysterious Stranger owes Corvin Ashby.")).toBeVisible();
  await expect(l.getByText("Nothing waits for review, and no boon is flagged.")).toBeVisible();

  // It stands in the ledger, with its review in its log; and the report is gone from the player's tab.
  await l.getByRole("tab", { name: /^Open/ }).click();
  const standing = l.getByRole("list", { name: "Boons" }).getByRole("listitem", { name: "Mysterious Stranger owes Corvin Ashby, minor" });
  await standing.getByRole("button", { name: "Open" }).click();
  const log = standing.getByRole("list", { name: "Log of Mysterious Stranger owes Corvin Ashby" });
  await expect(log).toContainText("Reported for review");
  await expect(log).toContainText("Accepted");
  await expect(log).toContainText("Confirmed with the Harpy");
  await p.reload();
  await expect(p.getByRole("region", { name: "Boons" }).getByRole("form", { name: "Report a boon" })).toBeVisible();
  await expect(p.getByRole("list", { name: "Your reports" })).toHaveCount(0);
});

test("the Harpy keeps the ledger from the Play View as their character, and never sees what an edit changed (#688)", async ({ browser }) => {
  const custodian = await person(browser, "bharpy-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bharpy-lead");
  const harpy = await person(browser, "bharpy-harpy");
  const player = await person(browser, "bharpy-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Debts Kept ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const philippa = await home(harpy.page, "Philippa Quill");
  await home(player.page, "Edric Thorne");
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/characters/${philippa}/titles`, { titles: ["Harpy"] });

  // The lead gives the Harpy the full ledger.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/settings`);
  const full = l.getByRole("radio", { name: /^The full ledger/ });
  await full.check();
  await expect(l.getByText("Saved: The Harpy keeps the full ledger, and reviews the boons players report.")).toBeVisible();
  await expect(full).toBeChecked();

  // Philippa's player opens the ledger from her Play View's Boons tab, and registers a boon.
  const h = harpy.page;
  await h.goto(`/play/characters/${philippa}?tab=boons`);
  const card = h.getByRole("region", { name: "Boons" }).getByText(`Philippa Quill, Harpy of Debts Kept ${run}`);
  await expect(card).toBeVisible();
  await h.getByRole("link", { name: "Open the boon ledger" }).click();
  await expect(h.getByRole("heading", { name: "The boon ledger" })).toBeVisible();
  await expect(h.getByText(`As Harpy of Debts Kept ${run}.`)).toBeVisible();
  await h.getByRole("button", { name: "Register boons" }).click();
  const entry = h.getByRole("form", { name: "Register boons" });
  await entry.getByLabel("Date for new rows").fill("2026-10-03");
  const row = entry.getByRole("listitem", { name: "Boon 1" });
  await row.getByRole("combobox", { name: "Debtor" }).fill("Edric");
  await row.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Edric Thorne/ }).click();
  await row.getByRole("combobox", { name: "Creditor" }).fill("Lady Ashgrove");
  await row.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /name only/ }).click();
  await row.getByLabel("Reason").fill("Safe passage");
  await entry.getByRole("button", { name: "Register the boon" }).click();
  await expect(h.getByText("Registered a boon.")).toBeVisible();

  // She corrects it, with a note: her log shows the edit as hers, not what it changed.
  const boons = h.getByRole("list", { name: "Boons" });
  const debt = boons.getByRole("listitem", { name: "Edric Thorne owes Lady Ashgrove, minor" });
  await debt.getByRole("button", { name: "Open" }).click();
  await debt.getByRole("button", { name: "Edit" }).click();
  const edit = debt.getByRole("form", { name: "Edit: Edric Thorne owes Lady Ashgrove" });
  await expect(edit.getByLabel("Staff note")).toHaveCount(0);
  await edit.getByLabel("Kind").selectOption("major");
  await edit.getByLabel("Why the edit").fill("Misheard at Elysium");
  await edit.getByRole("button", { name: "Save the edit" }).click();
  const theirs = boons.getByRole("listitem", { name: "Edric Thorne owes Lady Ashgrove, major" });
  const theirLog = theirs.getByRole("list", { name: "Log of Edric Thorne owes Lady Ashgrove" });
  await expect(theirLog).toContainText("Misheard at Elysium");
  await expect(theirLog).toContainText("Philippa Quill");
  await expect(theirLog).not.toContainText("Kind: Minor → Major");
  await h.screenshot(shots("harpy-ledger"));

  // The lead sees the same edit, what it changed, and that Philippa made it.
  await l.goto(`/troupes/${troupe.id}/boons`);
  const staffRow = l.getByRole("list", { name: "Boons" }).getByRole("listitem", { name: "Edric Thorne owes Lady Ashgrove, major" });
  await staffRow.getByRole("button", { name: "Open" }).click();
  const staffLog = staffRow.getByRole("list", { name: "Log of Edric Thorne owes Lady Ashgrove" });
  await expect(staffLog).toContainText("Kind: Minor → Major");
  await expect(staffLog).toContainText("as Philippa Quill");
});

test("the Harpy gives a Lesser Harpy add-only access: they register a boon as their character but can't edit it (#689)", async ({ browser }) => {
  const custodian = await person(browser, "btalon-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "btalon-lead");
  const harpy = await person(browser, "btalon-harpy");
  const talon = await person(browser, "btalon-talon");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Talons Kept ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const morwen = await home(harpy.page, "Morwen Vale");
  const wren = await home(talon.page, "Wren Ashby");
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-harpy`, { access: "full" });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/characters/${morwen}/titles`, { titles: ["Harpy"] });

  // The lead lets the Harpy give others access.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/settings`);
  const lets = l.getByRole("checkbox", { name: /^The Harpy may give others access to the ledger/ });
  await lets.check();
  await expect(l.getByText("Saved: the Harpy may give others access to the ledger, as Lesser Harpies.")).toBeVisible();

  // Morwen's player makes Wren a Lesser Harpy who may add boons, nothing more.
  const h = harpy.page;
  await h.goto(`/play/characters/${morwen}/ledger`);
  await h.getByLabel("Make a Lesser Harpy").selectOption({ label: "Wren Ashby" });
  const may = h.getByRole("group", { name: "What they may do" });
  await expect(may.getByLabel("Add boons")).toBeChecked();
  await expect(may.getByLabel("Edit boons")).not.toBeChecked();
  await h.getByRole("button", { name: "Give access" }).click();
  await expect(h.getByText("Wren Ashby has access to the ledger.")).toBeVisible();
  await expect(h.getByRole("list", { name: "Lesser Harpies" })).toContainText("Wren Ashby sees the ledger and adds boons");

  // Wren's player opens the ledger from her Play View, and registers a boon as Wren.
  const t = talon.page;
  await t.goto(`/play/characters/${wren}?tab=boons`);
  await expect(t.getByRole("region", { name: "Boons" }).getByText(`Wren Ashby, Lesser Harpy of Talons Kept ${run}`)).toBeVisible();
  await t.getByRole("link", { name: "Open the boon ledger" }).click();
  await expect(t.getByText(`As a Lesser Harpy of Talons Kept ${run}.`)).toBeVisible();
  await t.getByRole("button", { name: "Register boons" }).click();
  const entry = t.getByRole("form", { name: "Register boons" });
  await entry.getByLabel("Date for new rows").fill("2026-10-03");
  const row = entry.getByRole("listitem", { name: "Boon 1" });
  await row.getByRole("combobox", { name: "Debtor" }).fill("Wren");
  await row.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Wren Ashby/ }).click();
  await row.getByRole("combobox", { name: "Creditor" }).fill("Lady Morrow");
  await row.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /name only/ }).click();
  await row.getByLabel("Reason").fill("A word at court");
  await entry.getByRole("button", { name: "Register the boon" }).click();
  await expect(t.getByText("Registered a boon.")).toBeVisible();

  // She can open it, but not edit, settle or void it.
  const debt = t.getByRole("list", { name: "Boons" }).getByRole("listitem", { name: "Wren Ashby owes Lady Morrow, minor" });
  await debt.getByRole("button", { name: "Open" }).click();
  await expect(debt.getByRole("list", { name: "Log of Wren Ashby owes Lady Morrow" })).toContainText("Wren Ashby");
  await expect(debt.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await expect(debt.getByRole("button", { name: "Settle" })).toHaveCount(0);
  await t.screenshot(shots("talon-ledger"));
});

test("staff declare a Boonbreaker: their open boons are made void, both ways, and they hold Disgraced while the mark stands (#717)", async ({ browser }) => {
  const custodian = await person(browser, "bbreak-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bbreak-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Broken Promises ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  // Ottavia, a Camarilla NPC, owes Lucan a boon and is owed one by him.
  const ottavia = await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Ottavia Sterne", wizard: false });
  await send(l, "PUT", `/api/characters/${ottavia.id}/npc/ratings`, { category: "sect", name: "Camarilla", rating: null, detail: "" });
  const lucan = await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Lucan Mireaux", wizard: false });
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  const owes = (debtor: string, creditor: string, kind: string, reason: string) => ({
    debtor: { character_id: debtor },
    creditor: { character_id: creditor },
    kind,
    made_on: "2026-10-03",
    reason,
  });
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [owes(ottavia.id, lucan.id, "major", "Passage through the docks"), owes(lucan.id, ottavia.id, "minor", "A quiet word")],
  });

  await l.goto(`/troupes/${troupe.id}`);
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: "Boons", exact: true }).click();
  await expect(l.getByText("No Boonbreakers.")).toBeVisible();

  // Before declaring it, staff see what it makes void.
  await l.getByRole("button", { name: "Declare a Boonbreaker" }).click();
  const declare = l.getByRole("form", { name: "Declare a Boonbreaker" });
  await declare.getByLabel("Who").selectOption({ label: "Ottavia Sterne" });
  await expect(declare.getByRole("status")).toHaveText("This makes 2 boons void: 1 owed by them, 1 owed to them.");
  await declare.getByLabel("The boon they refused (optional)").selectOption({ label: "Ottavia Sterne owes Lucan Mireaux, major: Passage through the docks" });
  await declare.getByLabel("What they refused, and when").fill("Refused the Harpy at Elysium, 7 November");
  await declare.getByRole("button", { name: "Declare them a Boonbreaker" }).click();

  const mark = l.getByRole("list", { name: "Boonbreakers" }).getByRole("listitem", { name: "Ottavia Sterne, Boonbreaker" });
  await expect(mark).toContainText("2 boons made void · holds Disgraced for it");
  await expect(mark).toContainText("Refused: Ottavia Sterne owes Lucan Mireaux, major");
  await expect(l.getByRole("tab", { name: /^Open/ })).toContainText("(0)");
  await l.getByRole("tab", { name: /^Void/ }).click();
  const voided = l.getByRole("list", { name: "Boons" }).getByRole("listitem", { name: "Ottavia Sterne owes Lucan Mireaux, major" });
  await expect(voided).toContainText("Boonbreaker");
  await expect(voided).toContainText("Void");
  await l.screenshot(shots("boonbreaker-declared"));

  // Disgraced, on her status, for as long as the mark stands.
  await l.goto(`/characters/${ottavia.id}/status`);
  const card = l.locator("section").filter({ has: l.getByRole("heading", { name: "Status", exact: true }) });
  await expect(card.getByRole("listitem", { name: "Disgraced" })).toContainText("While a Boonbreaker (p. 397).");
});

test("the Harpy audits a character's boons and gives it to another, whose player reads it as it stood (#690)", async ({ browser }) => {
  const custodian = await person(browser, "baudit-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "baudit-lead");
  const harpy = await person(browser, "baudit-harpy");
  const reader = await person(browser, "baudit-reader");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Audits Kept ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const isolde = await home(harpy.page, "Isolde Fenwick");
  const corin = await home(reader.page, "Corin Halloway");
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-harpy`, { access: "full" });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/characters/${isolde}/titles`, { titles: ["Harpy"] });
  const debt = { debtor: { character_id: isolde }, creditor: { name: "Lady Morrow" }, kind: "major", made_on: "2026-10-03", reason: "A secret kept" };
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/boons`, { boons: [debt], note: "" });

  // Isolde's player, as the Harpy, audits Isolde's boons for Corin from the ledger.
  const h = harpy.page;
  await h.goto(`/play/characters/${isolde}/ledger`);
  await h.getByLabel("Audit", { exact: true }).selectOption({ label: "Isolde Fenwick" });
  await h.getByLabel("Give it to", { exact: true }).selectOption({ label: "Corin Halloway" });
  await h.getByRole("button", { name: "Make the audit" }).click();
  await expect(h.getByText("Audited Isolde Fenwick's boons, and gave it to Corin Halloway.")).toBeVisible();
  await expect(h.getByRole("list", { name: "Audits" })).toContainText("given to Corin Halloway");

  // Corin's player finds it in the Play View's Boons tab and reads it.
  const r = reader.page;
  await r.goto(`/play/characters/${corin}?tab=boons`);
  await r.getByRole("list", { name: "Audits" }).getByRole("link", { name: "Isolde Fenwick's boons" }).click();
  await expect(r.getByRole("heading", { name: "Boon audit · Isolde Fenwick" })).toBeVisible();
  await expect(r.getByText("owes 1 (weighing 3) · is owed 0")).toBeVisible();
  const owes = r.getByRole("region", { name: "Boons Isolde Fenwick owes" });
  await expect(owes).toContainText("Lady Morrow");
  await expect(owes).toContainText("A secret kept");
  await expect(owes).toContainText("Standing");
  await r.screenshot(shots("boon-audit"));
});
