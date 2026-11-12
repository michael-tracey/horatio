import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, person, makeCustodian, builtVampire, ATTRIBUTES_AND_FOCUSES, backstoryOptional, shots } from "./support";

/** Boons: the troupe's ledger, for its running staff: registering a game's boons at once, settling, editing and trading them, each with its own log; and the Play View's Boons tab, where players report boons and see what the troupe lets them (#686). */

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
