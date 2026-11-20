import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, person, makeCustodian, builtVampire, ATTRIBUTES_AND_FOCUSES, backstoryOptional, shots, troupeTab, tabSettings } from "./support";

/** Boons: the troupe's ledger, for its running staff: registering a game's boons at once, settling, editing and trading them, each with its own log; the boon standings; the Play View's Boons tab, where players report boons and see what the troupe lets them (#686); review, where reports wait for staff to accept them (#687); the Harpy keeping the ledger as their character (#688); and Lesser Harpies the Harpy gives access (#689). */

closeContextsAfterEach();

/**
 * The boon ledger's table (#975): a row for each boon, named "Agnes owes Bram, minor",
 * opened by a click on it into the side panel (#979), its detail a region named
 * "Boon: Agnes owes Bram, minor", with what to do with it in its Actions menu.
 */
function ledgerOf(page: Page) {
  // Not while it shows the rows before, dimmed, and waits for the view's own (#1031).
  const table = page.getByRole("table", { name: "Boons" }).and(page.locator(":not([aria-busy])"));
  const row = (name: string) => table.getByRole("row", { name, exact: true });
  const actions = (name: string) => page.getByRole("button", { name: `Actions: ${name}`, exact: true });
  return {
    table,
    row,
    // One chevron for each boon: the rows without the headings.
    rows: table.getByRole("button", { name: /^Details: / }),
    detail: (name: string) => page.getByRole("region", { name: `Boon: ${name}`, exact: true }),
    actions,
    /** Opens a boon from its row (the first, of several alike), closing the one open first: over the whole page, on a phone. */
    open: async (name: string) => {
      if (await page.locator("dialog[open]").count()) await page.keyboard.press("Escape");
      await expect(page.locator("dialog[open]")).toHaveCount(0);
      await row(name).first().click();
    },
    /** Escape closes the open boon. */
    close: async () => {
      await page.keyboard.press("Escape");
      await expect(page.getByRole("region", { name: /^Boon: / })).toHaveCount(0);
    },
    /** Chooses one of the open boon's actions from its Actions menu. */
    act: async (name: string, action: string) => {
      await actions(name).click();
      await page.getByRole("menu", { name: `Actions: ${name}` }).getByRole("menuitem", { name: action, exact: true }).click();
    },
  };
}

// The ledger's views (#976), by the value each has: side by side from lg up, a select on a phone.
const VIEW_NAMES = { open: "Open", departed: "Departed", settled: "Settled", void: "Void", all: "All" } as const;
type LedgerView = keyof typeof VIEW_NAMES;
const onPhone = () => test.info().project.name === "phone";

/** A view of the ledger, which holds its count while a search narrows it: "Open (4)". */
function viewOf(page: Page, view: LedgerView) {
  return onPhone()
    ? page.getByRole("combobox", { name: "Ledger views" }).locator(`option[value="${view}"]`)
    : page.getByRole("radiogroup", { name: "Ledger views" }).getByRole("radio", { name: new RegExp(`^${VIEW_NAMES[view]}( \\(|$)`) });
}

/** A number in the totals strip above the toolbar (#977), the whole ledger's, named "Open 4" or "Minor 2". */
function totalOf(page: Page, label: string) {
  return page.getByRole("group", { name: "The whole ledger" }).getByRole("button", { name: new RegExp(`^${label} [\\d,]+$`) });
}

/** To review's number in the totals strip, which opens its tab (#982). */
function reviewTotal(page: Page) {
  return page.getByRole("group", { name: "The whole ledger" }).getByRole("link", { name: /^To review [\d,]+$/ });
}

/** A tab of the boons screen (#982): Ledger, To review, Standings, Statistics, Boonbreakers or Audits, with any count after it. */
function boonTab(page: Page, name: string) {
  return page.getByRole("navigation", { name: "Boons", exact: true }).getByRole("link", { name: new RegExp(`^${name}( \\d+ \\w+)?$`) });
}

async function showView(page: Page, view: LedgerView) {
  if (onPhone()) await page.getByRole("combobox", { name: "Ledger views" }).selectOption(view);
  else await viewOf(page, view).click();
}

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

  // The ledger is off by default. The lead switches it on in the Features list of the troupe's settings.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/settings`);
  const keep = l.getByRole("list", { name: "Features" }).getByRole("switch", { name: "Boons" });
  await expect(keep).toHaveAttribute("aria-checked", "false");
  await keep.click();
  await expect(l.getByText("Boons: switched on.")).toBeVisible();
  await expect(keep).toHaveAttribute("aria-checked", "true");

  // Under Court, the Boons screen: register a game's boons at once, in a dialog from the toolbar (#983).
  await troupeTab(l, "Boons");
  await expect(l.getByText("No open boons yet.")).toBeVisible();
  await l.getByRole("button", { name: "Register boons" }).click();
  const dialog = l.getByRole("dialog", { name: "Register boons" });
  const entry = dialog.getByRole("form", { name: "Register boons" });
  await entry.getByLabel("Date for new rows").fill("2026-10-03");
  await entry.getByLabel("Where they come from (optional)").fill("Elysium, 3 October");
  const pick = async (row: ReturnType<Page["getByRole"]>, side: "Debtor" | "Creditor", typed: string, option: RegExp) => {
    await row.getByRole("combobox", { name: side }).fill(typed);
    await row.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: option }).click();
  };
  const first = entry.getByRole("listitem", { name: "Boon 1" });
  await pick(first, "Debtor", "Mireille", /Mireille Dauvin/);
  // Leaving with a row started asks first; Cancel keeps the form as it was.
  await l.keyboard.press("Escape");
  const discard = l.getByRole("dialog", { name: "Discard these boons?" });
  await discard.getByRole("button", { name: "Cancel" }).click();
  await expect(discard).toBeHidden();
  await expect(first.getByRole("combobox", { name: "Debtor" })).toHaveValue(/Mireille Dauvin/);
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
  await expect(dialog).toBeHidden();

  const boons = ledgerOf(l);
  await expect(boons.row("Mireille Dauvin owes Anselm Roque, minor")).toHaveCount(3);
  await expect(totalOf(l, "Open")).toHaveAccessibleName("Open 4");
  // One line each (#975): a name only, someone not in Horatio, in italics.
  const vargaRow = boons.row("Elder Varga owes Mireille Dauvin, trivial");
  // (A phone's first line repeats the creditor, and its fold the state, so each is looked for where it shows.)
  const shown = (text: string) => vargaRow.getByText(text, { exact: true }).filter({ visible: true });
  await expect(shown("Elder Varga")).toHaveCSS("font-style", "italic");
  await expect(shown("Mireille Dauvin")).toHaveCSS("font-style", "normal");
  await expect(vargaRow).toContainText("Introduction");
  // A name that links to no character is flagged for review (#687), and the row says so.
  await expect(shown("Flagged")).toBeVisible();

  // One of the three is called in: it leaves the open boons for the settled. A click on its row opens it.
  await boons.open("Mireille Dauvin owes Anselm Roque, minor");
  const owed = boons.detail("Mireille Dauvin owes Anselm Roque, minor");
  await expect(owed).toContainText("Secret");
  await boons.act("Mireille Dauvin owes Anselm Roque, minor", "Settle");
  const settle = owed.getByRole("form", { name: "Settle: Mireille Dauvin owes Anselm Roque" });
  await settle.getByLabel(/^Called in/).check();
  await settle.getByLabel("Note (optional)").fill("Called in for a favour at court");
  await settle.getByRole("button", { name: "Settle it" }).click();
  await expect(totalOf(l, "Open")).toHaveAccessibleName("Open 3");
  await expect(totalOf(l, "Settled")).toHaveAccessibleName("Settled 1");
  await boons.close();
  await showView(l, "settled");
  await expect(boons.rows).toHaveCount(1);
  await expect(boons.row("Mireille Dauvin owes Anselm Roque, minor")).toContainText("Settled: called in");
  // The chevron opens it too, from the keyboard.
  await boons.row("Mireille Dauvin owes Anselm Roque, minor").getByRole("button", { name: "Details: Mireille Dauvin owes Anselm Roque, minor" }).click();
  const settledLog = boons.detail("Mireille Dauvin owes Anselm Roque, minor").getByRole("list", { name: "Log of Mireille Dauvin owes Anselm Roque" });
  await expect(settledLog).toContainText("Elysium, 3 October");
  await expect(settledLog).toContainText("Called in for a favour at court");

  // The trivial boon was typed in wrong: an edit, with why, keeps what changed in its log.
  await boons.close();
  await showView(l, "open");
  await expect(boons.rows).toHaveCount(3);
  await boons.open("Elder Varga owes Mireille Dauvin, trivial");
  const varga = boons.detail("Elder Varga owes Mireille Dauvin, trivial");
  await boons.act("Elder Varga owes Mireille Dauvin, trivial", "Edit");
  const edit = varga.getByRole("form", { name: "Edit: Elder Varga owes Mireille Dauvin" });
  await edit.getByLabel("Kind").selectOption("minor");
  await edit.getByLabel("Why the edit").fill("Typed in wrong");
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  const edited = boons.detail("Elder Varga owes Mireille Dauvin, minor");
  await expect(edited.getByRole("list", { name: "Log of Elder Varga owes Mireille Dauvin" })).toContainText("Kind: Trivial → Minor");

  // Anselm trades one of his to Elder Varga: the boon keeps its history.
  await boons.open("Mireille Dauvin owes Anselm Roque, minor");
  const held = boons.detail("Mireille Dauvin owes Anselm Roque, minor");
  await boons.act("Mireille Dauvin owes Anselm Roque, minor", "Trade");
  const trade = held.getByRole("form", { name: "Trade: Mireille Dauvin owes Anselm Roque" });
  await trade.getByRole("combobox", { name: "Traded to" }).fill("Elder Varga");
  await trade.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /name only/ }).click();
  await trade.getByRole("button", { name: "Record the trade" }).click();
  const traded = boons.detail("Mireille Dauvin owes Elder Varga, minor");
  await expect(traded.getByRole("list", { name: "Log of Mireille Dauvin owes Elder Varga" })).toContainText("Creditor: Anselm Roque → Elder Varga");

  // On Mireille's sheet, staff see what she owes and is owed, with a way into the ledger: her own page of it (#980).
  await l.goto(`/characters/${mireille}`);
  const card = l.getByRole("listitem", { name: `Boons in Ledger of Debts ${run}` });
  await expect(card).toContainText("Owes: 2 minor");
  await expect(card).toContainText("Is owed: 1 minor");
  await card.getByRole("link", { name: "In the boon ledger" }).click();
  await expect(l.getByRole("table", { name: "Owes", exact: true }).getByRole("button", { name: /^Details: / })).toHaveCount(2);
  await expect(l.getByRole("table", { name: "Is owed", exact: true }).getByRole("button", { name: /^Details: / })).toHaveCount(1);

  // Her player isn't shown her boons (that comes with #686), and can't open the ledger.
  const p = player.page;
  const mine = await p.request.get(`/api/characters/${mireille}/boons`);
  expect((await mine.json()).troupes).toEqual([]);
  const refused = await p.request.get(`/api/troupes/${troupe.id}/boons`);
  expect(refused.status()).toBe(403);
});

test("a boon opens in a side panel from its row or a link, facts first, what to do in its Actions menu, and Escape or Back closes it (#979)", async ({ browser }) => {
  const custodian = await person(browser, "bpanel-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bpanel-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Ledger at the Side ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [
      { debtor: { name: "Oriel Vance" }, creditor: { name: "Saskia Brandt" }, kind: "minor", made_on: "2026-09-12", reason: "A quiet word with the Sheriff", conditions: "Cannot be traded" },
      { debtor: { name: "Teodor Lisk" }, creditor: { name: "Saskia Brandt" }, kind: "trivial", made_on: "2026-09-10", reason: "Directions to a haven" },
    ],
    note: "",
  });
  // 375 px on a phone; the desktop's 1280.
  if (onPhone()) await l.setViewportSize({ width: 375, height: 800 });
  await l.goto(`/troupes/${troupe.id}/boons`);
  const boons = ledgerOf(l);
  const oriel = "Oriel Vance owes Saskia Brandt, minor";
  const chevron = boons.row(oriel).getByRole("button", { name: `Details: ${oriel}` });

  // A click on its row opens it: beside the table, the row marked, from lg up; over the whole screen on a phone.
  await boons.row(oriel).click();
  const panel = (title: string) => (onPhone() ? l.getByRole("dialog", { name: title }) : l.getByRole("complementary", { name: title }));
  await expect(panel("Oriel Vance owes Saskia Brandt")).toBeVisible();
  await expect(chevron).toHaveAttribute("aria-current", "true");
  const box = (await panel("Oriel Vance owes Saskia Brandt").boundingBox())!;
  if (onPhone()) expect(box.width).toBe(375);
  // Beside the table at 1280, and at 1024 where lg starts, with nothing sideways.
  const besideTable = async () => {
    const table = (await boons.table.boundingBox())!;
    expect((await panel("Oriel Vance owes Saskia Brandt").boundingBox())!.x).toBeGreaterThanOrEqual(table.x + table.width);
  };
  const noSideways = async () => expect(await l.evaluate(() => document.documentElement.scrollWidth)).toBe(l.viewportSize()!.width);
  if (!onPhone()) {
    await besideTable();
    await l.setViewportSize({ width: 1024, height: 720 });
    await besideTable();
    await noSideways();
    await l.setViewportSize({ width: 1280, height: 720 });
  }
  await noSideways();
  // Its facts first, the reason and conditions in full, its log last; what to do is in the menu, not in buttons.
  const detail = boons.detail(oriel);
  await expect(detail).toContainText("A quiet word with the Sheriff");
  await expect(detail).toContainText("Cannot be traded");
  await expect(detail.getByRole("button", { name: "Settle" })).toHaveCount(0);
  await expect(detail.getByRole("list", { name: "Log of Oriel Vance owes Saskia Brandt" })).toContainText("Registered");
  // It is in the address; Escape closes it and gives its row the focus back.
  const id = new URL(l.url()).searchParams.get("boon");
  expect(id).toBeTruthy();
  await l.keyboard.press("Escape");
  await expect(detail).toHaveCount(0);
  await expect(chevron).toBeFocused();
  expect(new URL(l.url()).searchParams.get("boon")).toBeNull();

  // A link opens it too, with the rest of the search kept; Back closes one opened from its row.
  await l.goto(`/troupes/${troupe.id}/boons?kind=minor&boon=${id}`);
  await expect(detail).toBeVisible();
  await expect(boons.rows).toHaveCount(1);
  await l.keyboard.press("Escape");
  await expect(detail).toHaveCount(0);
  expect(new URL(l.url()).searchParams.get("kind")).toBe("minor");
  await boons.row(oriel).click();
  await expect(detail).toBeVisible();
  await l.goBack();
  await expect(detail).toHaveCount(0);
  await expect(boons.rows).toHaveCount(1);
  // A phone's dialog says it has closed a moment after it goes: a view chosen in that moment is kept, and the boon
  // stays closed (#1025). Here the view changes, then the dialog says it closed, before the page has caught up.
  if (onPhone()) {
    await boons.open(oriel);
    await expect(detail).toBeVisible();
    await l.evaluate(() => {
      const views = document.querySelector<HTMLSelectElement>('select[aria-label="Ledger views"]')!;
      views.value = "all";
      views.dispatchEvent(new Event("change", { bubbles: true }));
      const dialog = document.querySelector("dialog[open]")!;
      dialog.close();
      dialog.dispatchEvent(new Event("close"));
    });
    await expect(l).toHaveURL((url) => url.searchParams.get("view") === "all" && !url.searchParams.has("boon"));
    await expect(detail).toHaveCount(0);
    await showView(l, "open");
  }

  // Each action is in its Actions menu, Make void apart at its foot, and shows its form in the panel.
  await boons.open(oriel);
  await boons.actions(oriel).click();
  const menu = l.getByRole("menu", { name: `Actions: ${oriel}` });
  await expect(menu.getByRole("menuitem")).toHaveText(["Edit", "Trade", "Pass on", "Settle", "Make void"]);
  await expect(menu.getByRole("group", { name: "Close or reopen it" }).getByRole("menuitem")).toHaveText(["Make void"]);
  await l.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(detail).toBeVisible();

  await boons.act(oriel, "Edit");
  const edit = detail.getByRole("form", { name: "Edit: Oriel Vance owes Saskia Brandt" });
  await edit.getByLabel("Reason").fill("A quiet word with the Prince");
  await edit.getByLabel("Why the edit").fill("Misheard");
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  await expect(edit).toHaveCount(0);
  // Staff see what it changed, struck through and beside it, marked as theirs alone.
  const log = detail.getByRole("list", { name: "Log of Oriel Vance owes Saskia Brandt" });
  await expect(log).toContainText("Reason: A quiet word with the Sheriff → A quiet word with the Prince");
  await expect(log.getByText("Staff only")).toBeVisible();
  await expect(log.getByRole("deletion")).toHaveText("A quiet word with the Sheriff");

  await boons.act(oriel, "Trade");
  const trade = detail.getByRole("form", { name: "Trade: Oriel Vance owes Saskia Brandt" });
  await trade.getByRole("combobox", { name: "Traded to" }).fill("Ines Harrow");
  await trade.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /name only/ }).click();
  await trade.getByRole("button", { name: "Record the trade" }).click();
  const traded = "Oriel Vance owes Ines Harrow, minor";
  await expect(boons.detail(traded)).toContainText("Creditor: Saskia Brandt → Ines Harrow");

  await boons.act(traded, "Pass on");
  const pass = boons.detail(traded).getByRole("form", { name: "Pass on: Oriel Vance owes Ines Harrow" });
  await pass.getByRole("combobox", { name: "Passes on to" }).fill("Corin Vance");
  await pass.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /name only/ }).click();
  await pass.getByRole("button", { name: "Pass it on" }).click();
  const corin = "Corin Vance owes Ines Harrow, minor";
  await expect(boons.detail(corin)).toContainText("Debtor: Oriel Vance → Corin Vance");

  await boons.act(corin, "Settle");
  const settle = boons.detail(corin).getByRole("form", { name: "Settle: Corin Vance owes Ines Harrow" });
  await settle.getByLabel(/^Called in/).check();
  await settle.getByRole("button", { name: "Settle it" }).click();
  await expect(boons.detail(corin)).toContainText("Settled: called in");

  await boons.act(corin, "Make void");
  const voiding = boons.detail(corin).getByRole("form", { name: "Make void: Corin Vance owes Ines Harrow" });
  await voiding.getByLabel("Why").fill("Entered twice");
  await voiding.getByRole("button", { name: "Make it void" }).click();
  await expect(boons.detail(corin).getByRole("list", { name: "Log of Corin Vance owes Ines Harrow" })).toContainText("State: Settled → Void");

  await boons.act(corin, "Reopen");
  const reopen = boons.detail(corin).getByRole("form", { name: "Reopen: Corin Vance owes Ines Harrow" });
  await reopen.getByLabel("Why").fill("Not twice after all");
  await reopen.getByRole("button", { name: "Reopen it" }).click();
  const corinLog = boons.detail(corin).getByRole("list", { name: "Log of Corin Vance owes Ines Harrow" });
  await expect(corinLog.getByRole("listitem").filter({ hasText: /^Reopened/ })).toContainText("Not twice after all");
  await expect(corinLog).toContainText("Edited");
  await expect(corinLog).toContainText("Traded");
  await expect(corinLog).toContainText("Passed on");
  await expect(corinLog).toContainText("Settled");
  await expect(corinLog).toContainText("Made void");
  await l.screenshot(shots("boon-panel"));
  await boons.close();
  await expect(boons.row(corin).getByRole("button", { name: `Details: ${corin}` })).toBeFocused();
});

test("the ledger shows a hundred boons a page, with Previous and Next, and the page in the URL (#978)", async ({ browser }) => {
  const custodian = await person(browser, "pager-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "pager-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Ledger by the Page ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  // 140 boons, twenty a month from January to July: July's are the newest.
  const rows = [1, 2, 3, 4, 5, 6, 7].map((month) => ({
    debtor: { name: `Debtor of month ${month}` },
    creditor: { name: "Hesper Calloway" },
    kind: "minor",
    made_on: `2026-0${month}-01`,
    reason: `Favour of month ${month}`,
    count: 20,
  }));
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, { boons: rows, note: "" });

  await l.goto(`/troupes/${troupe.id}/boons`);
  const boons = ledgerOf(l);
  const pages = l.getByRole("navigation", { name: "Pages of boons" });
  await expect(pages).toContainText("1 to 100 of 140");
  await expect(boons.rows).toHaveCount(100);
  await expect(boons.row("Debtor of month 7 owes Hesper Calloway, minor")).toHaveCount(20);
  await expect(pages.getByRole("button", { name: "Previous" })).toBeDisabled();
  // The ledger opens on its boons (#982): the first is in sight as the page opens, on a 375 px phone (as tall as
  // layout.spec.ts's) as at 1280 px.
  const screenSize = onPhone() ? { width: 375, height: 800 } : { width: 1280, height: 720 };
  await l.setViewportSize(screenSize);
  await l.screenshot({ ...shots("ledger-first-screen"), fullPage: false });
  const first = (await boons.rows.first().boundingBox())!;
  expect(first.y + first.height).toBeLessThanOrEqual(screenSize.height);

  // The next page has the oldest 40, and the URL says which page it is.
  await pages.getByRole("button", { name: "Next" }).click();
  await expect(pages).toContainText("101 to 140 of 140");
  await expect(l).toHaveURL(/[?&]page=2\b/);
  await expect(boons.rows).toHaveCount(40);
  await expect(boons.row("Debtor of month 1 owes Hesper Calloway, minor")).toHaveCount(20);
  await expect(boons.row("Debtor of month 7 owes Hesper Calloway, minor")).toHaveCount(0);
  await expect(pages.getByRole("button", { name: "Next" })).toBeDisabled();
  // A reload keeps the page.
  await l.reload();
  await expect(pages).toContainText("101 to 140 of 140");
  await expect(boons.rows).toHaveCount(40);
  // Back to the first page.
  await pages.getByRole("button", { name: "Previous" }).click();
  await expect(pages).toContainText("1 to 100 of 140");
  await expect(l).not.toHaveURL(/page=/);

  // Another view starts from its first page; one that fits on a page needs no pager.
  await pages.getByRole("button", { name: "Next" }).click();
  await expect(l).toHaveURL(/[?&]page=2\b/);
  await showView(l, "all");
  await expect(l).not.toHaveURL(/page=/);
  await expect(pages).toContainText("1 to 100 of 140");
  await showView(l, "settled");
  await expect(l.getByText("None here.")).toBeVisible();
  await expect(pages).toHaveCount(0);
  // An old link past the last page shows the last there is.
  await l.goto(`/troupes/${troupe.id}/boons?page=9`);
  await expect(pages).toContainText("101 to 140 of 140");
  await expect(l).toHaveURL(/[?&]page=2\b/);
});

test("the ledger's toolbar searches the reason and conditions, picks kinds, filters by night and sorts, all kept in the URL (#976), and the totals strip shows a view or a kind (#977)", async ({ browser }) => {
  const custodian = await person(browser, "toolbar-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "toolbar-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Ledger Toolbar ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  const boon = (debtor: string, creditor: string, kind: string, made_on: string, reason: string, conditions = "") => ({
    debtor: { name: debtor },
    creditor: { name: creditor },
    kind,
    made_on,
    reason,
    conditions,
  });
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [
      boon("Orsolya Venk", "Piet Marlowe", "minor", "2026-03-01", "Silence at the masquerade"),
      boon("Quintus Hale", "Orsolya Venk", "major", "2026-04-01", "Shelter from the hunters", "Cannot be traded"),
      boon("Rhea Solberg", "Quintus Hale", "trivial", "2026-05-01", "An introduction"),
      boon("Piet Marlowe", "Rhea Solberg", "life", "2026-02-01", "Saved from the sun"),
    ],
    note: "",
  });

  await l.goto(`/troupes/${troupe.id}/boons`);
  const boons = ledgerOf(l);
  await expect(boons.rows).toHaveCount(4);
  // The totals strip counts the whole ledger (#977); the views count only within a search.
  await expect(totalOf(l, "Open")).toHaveAccessibleName("Open 4");
  await expect(totalOf(l, "Minor")).toHaveAccessibleName("Minor 1");
  await expect(totalOf(l, "Blood")).toHaveAccessibleName("Blood 0");
  await expect(viewOf(l, "open")).not.toContainText("(");
  // Newest first, as it starts.
  await expect(boons.rows.first()).toHaveAccessibleName("Details: Rhea Solberg owes Quintus Hale, trivial");

  // Part of a reason narrows the list, and the views' counts follow; a reload keeps it.
  const searchBox = l.getByRole("searchbox", { name: "Search the ledger" });
  await searchBox.fill("MASQ");
  await expect(boons.rows).toHaveCount(1);
  await expect(boons.row("Orsolya Venk owes Piet Marlowe, minor")).toHaveCount(1);
  await expect(viewOf(l, "open")).toContainText("(1)");
  await expect(totalOf(l, "Open")).toHaveAccessibleName("Open 4");
  await expect(l).toHaveURL(/[?&]q=MASQ\b/);
  await l.reload();
  await expect(searchBox).toHaveValue("MASQ");
  await expect(boons.rows).toHaveCount(1);
  // The conditions, and a name only, any part of it.
  await searchBox.fill("traded");
  await expect(boons.rows).toHaveCount(1);
  await expect(boons.row("Quintus Hale owes Orsolya Venk, major")).toHaveCount(1);
  await searchBox.fill("solb");
  await expect(boons.rows).toHaveCount(2);
  await searchBox.fill("");
  await expect(boons.rows).toHaveCount(4);

  // Kinds, several at once; then More filters, with how many are set.
  const kinds = l.getByRole("group", { name: "Kinds" });
  await kinds.getByRole("button", { name: "Major" }).click();
  await kinds.getByRole("button", { name: "Life" }).click();
  await expect(boons.rows).toHaveCount(2);
  await expect(l).toHaveURL(/[?&]kind=major%2Clife\b/);
  await l.getByRole("button", { name: "More filters" }).click();
  await l.getByRole("group", { name: "More filters" }).getByLabel("Made from").fill("2026-03-01");
  await expect(boons.rows).toHaveCount(1);
  await expect(boons.row("Quintus Hale owes Orsolya Venk, major")).toHaveCount(1);
  await expect(l.getByRole("button", { name: "More filters, 1 set" })).toBeVisible();
  await l.getByRole("button", { name: "Show every boon" }).click();
  await expect(boons.rows).toHaveCount(4);
  await expect(l).not.toHaveURL(/kind=|from=/);

  // The column headings sort (from lg up); on a phone, the Order under More filters.
  if (onPhone()) {
    await l.getByRole("group", { name: "More filters" }).getByLabel("Order").selectOption({ label: "Kind, trivial to life" });
  } else {
    await boons.table.getByRole("button", { name: "Kind" }).click();
    await expect(boons.table.getByRole("columnheader", { name: "Kind" })).toHaveAttribute("aria-sort", "ascending");
  }
  await expect(boons.rows.first()).toHaveAccessibleName("Details: Rhea Solberg owes Quintus Hale, trivial");
  await expect(boons.rows.last()).toHaveAccessibleName("Details: Piet Marlowe owes Rhea Solberg, life");
  await expect(l).toHaveURL(/[?&]sort=kind\b/);
  if (!onPhone()) {
    await boons.table.getByRole("button", { name: "Kind" }).click();
    await expect(boons.rows.first()).toHaveAccessibleName("Details: Piet Marlowe owes Rhea Solberg, life");
    await expect(l).toHaveURL(/[?&]dir=desc\b/);
  }

  // A link reproduces the view: the view, the kinds, the order.
  await l.goto(`/troupes/${troupe.id}/boons?view=all&kind=minor,trivial&sort=debtor`);
  await expect(boons.rows).toHaveCount(2);
  await expect(boons.rows.first()).toHaveAccessibleName("Details: Orsolya Venk owes Piet Marlowe, minor");
  await expect(kinds.getByRole("button", { name: "Minor" })).toHaveAttribute("aria-pressed", "true");
  if (onPhone()) await expect(l.getByRole("combobox", { name: "Ledger views" })).toHaveValue("all");
  else await expect(viewOf(l, "all")).toHaveAttribute("aria-checked", "true");
  await l.screenshot(shots("boon-ledger-toolbar"));

  // A number in the totals strip shows just its boons (#977): the open majors, the search and filters cleared, the order kept.
  await searchBox.fill("solb");
  await expect(boons.rows).toHaveCount(1);
  await totalOf(l, "Major").click();
  await expect(boons.rows).toHaveCount(1);
  await expect(boons.row("Quintus Hale owes Orsolya Venk, major")).toHaveCount(1);
  await expect(searchBox).toHaveValue("");
  await expect(kinds.getByRole("button", { name: "Major" })).toHaveAttribute("aria-pressed", "true");
  await expect(totalOf(l, "Major")).toHaveAttribute("aria-current", "true");
  await expect(l).toHaveURL(/[?&]kind=major\b/);
  await expect(l).toHaveURL(/[?&]sort=debtor\b/);
  await expect(l).not.toHaveURL(/view=|q=/);
  await totalOf(l, "Open").click();
  await expect(boons.rows).toHaveCount(4);
  await totalOf(l, "Settled").click();
  await expect(l.getByText("None here.")).toBeVisible();
  // To review, for staff, who review: the names only wait there, flagged, under a tab of its own (#982).
  await expect(boonTab(l, "To review")).toHaveAccessibleName(/^To review \d+ waiting$/);
  await reviewTotal(l).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupe.id}/boons/review$`));
  await expect(l.getByRole("list", { name: "Boons to review" })).toBeVisible();
  await expect(boonTab(l, "To review")).toHaveAttribute("aria-current", "page");
  // An old link to the ledger's To review view opens the tab.
  await l.goto(`/troupes/${troupe.id}/boons?view=review`);
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupe.id}/boons/review$`));
  await expect(l.getByRole("list", { name: "Boons to review" })).toBeVisible();
});

test("a view of the ledger not read yet keeps the toolbar, the totals and the table on screen while it comes, the rows before dimmed (#1031)", async ({ browser }) => {
  const custodian = await person(browser, "unseen-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "unseen-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Ledger Unseen ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  const boon = (debtor: string, creditor: string, kind: string, made_on: string) => ({ debtor: { name: debtor }, creditor: { name: creditor }, kind, made_on, reason: "" });
  const made = await send(l, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [
      boon("Wendeline Asch", "Corvin Talbot", "minor", "2026-03-01"),
      boon("Corvin Talbot", "Wendeline Asch", "trivial", "2026-04-01"),
      boon("Ysolde Marrick", "Corvin Talbot", "major", "2026-05-01"),
      boon("Ysolde Marrick", "Wendeline Asch", "minor", "2026-06-01"),
    ],
    note: "",
  });
  await send(l, "POST", `/api/troupes/${troupe.id}/boons/${made[3].id}/void`, { note: "Entered twice" });

  await l.goto(`/troupes/${troupe.id}/boons`);
  const boons = ledgerOf(l);
  await expect(boons.rows).toHaveCount(3);
  // From here on, note anything of the ledger's frame that leaves the page, however briefly.
  await l.evaluate(() => {
    const frame = { toolbar: 'input[aria-label="Search the ledger"]', totals: '[role="group"][aria-label="The whole ledger"]', table: 'table[aria-label="Boons"]' };
    const gone: string[] = [];
    (window as unknown as { ledgerGone: string[] }).ledgerGone = gone;
    new MutationObserver(() => {
      for (const [name, selector] of Object.entries(frame)) if (!document.querySelector(selector) && !gone.includes(name)) gone.push(name);
    }).observe(document.body, { childList: true, subtree: true });
  });
  // The Void view's boons are held back until the test lets them come.
  let letThrough = () => {};
  const held = new Promise<void>((resolve) => (letThrough = resolve));
  await l.route(/\/api\/troupes\/[^/]+\/boons\?(.*&)?view=void\b/, async (route) => {
    await held;
    await route.continue();
  });
  await showView(l, "void");
  // While it comes: the open boons, dimmed and marked busy, under the toolbar and the totals.
  const waiting = l.getByRole("table", { name: "Boons" });
  await expect(waiting).toHaveAttribute("aria-busy", "true");
  await expect(waiting).toHaveClass(/opacity-60/);
  await expect(waiting.getByRole("button", { name: /^Details: / })).toHaveCount(3);
  await expect(l.getByRole("searchbox", { name: "Search the ledger" })).toBeVisible();
  await expect(totalOf(l, "Open")).toHaveAccessibleName("Open 3");
  letThrough();
  await expect(boons.rows).toHaveCount(1);
  await expect(boons.row("Ysolde Marrick owes Wendeline Asch, minor")).toHaveCount(1);
  await expect(waiting).not.toHaveAttribute("aria-busy");
  expect(await l.evaluate(() => (window as unknown as { ledgerGone: string[] }).ledgerGone)).toEqual([]);
});

test("the ledger groups its rows by debtor, creditor or night under headings with their count and weight, past the first five closed, kept in the URL; over 500 boons it waits for a narrower search (#981)", async ({ browser }) => {
  const custodian = await person(browser, "bgroup-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bgroup-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Ledger in Groups ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  // Seven debtors owe Isaura minor and major boons; 500 trivial ones from the filler make 509 open.
  const owed = (debtor: string, kind: string, made_on: string) => ({ debtor: { name: debtor }, creditor: { name: "Isaura Penhallow" }, kind, made_on, reason: `Owed by ${debtor}` });
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [
      owed("Aldric Vane", "major", "2026-03-07"),
      owed("Aldric Vane", "minor", "2026-03-07"),
      owed("Beatrix Moll", "minor", "2026-03-07"),
      owed("Cassius Thorn", "minor", "2026-03-07"),
      owed("Delphine Arkwright", "minor", "2026-02-07"),
      owed("Edmund Reyes", "minor", "2026-02-07"),
      owed("Fenella Grist", "minor", "2026-02-07"),
      owed("Gideon Hart", "minor", "2026-02-07"),
      owed("Gideon Hart", "minor", "2026-01-03"),
    ],
    note: "",
  });
  const filler = Array.from({ length: 25 }, (_, i) => ({
    debtor: { name: "Ledger filler" },
    creditor: { name: "Isaura Penhallow" },
    kind: "trivial",
    made_on: `2025-0${(i % 9) + 1}-1${i % 10}`,
    reason: `Filler ${i}`,
    count: 20,
  }));
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, { boons: filler, note: "" });

  // At a phone's 375 px and a desk's 1280 px.
  const width = onPhone() ? 375 : 1280;
  await l.setViewportSize({ width, height: onPhone() ? 800 : 720 });
  await l.goto(`/troupes/${troupe.id}/boons`);
  const boons = ledgerOf(l);
  const pages = l.getByRole("navigation", { name: "Pages of boons" });
  const groupBy = l.getByRole("combobox", { name: "Group by" });
  const heading = (name: string) => boons.table.getByRole("button", { name, exact: true });
  // 509 open boons: too many to group until the search is narrower.
  await expect(pages).toContainText("1 to 100 of 509");
  await expect(groupBy).toBeDisabled();
  await expect(groupBy).toHaveAccessibleDescription("Over 500 boons: narrow the search to group them.");

  // Minor and major boons only: nine, grouped by debtor, A to Z, the first five open.
  const kinds = l.getByRole("group", { name: "Kinds" });
  await kinds.getByRole("button", { name: "Minor" }).click();
  await kinds.getByRole("button", { name: "Major" }).click();
  await expect(boons.rows).toHaveCount(9);
  await expect(groupBy).toBeEnabled();
  await groupBy.selectOption({ label: "Debtor" });
  await expect(l).toHaveURL(/[?&]group=debtor\b/);
  const headings = boons.table.getByRole("rowheader");
  await expect(headings).toHaveText([
    /^Aldric Vane\s*2 boons · weight 4$/,
    /^Beatrix Moll\s*1 boon · weight 1$/,
    /^Cassius Thorn\s*1 boon · weight 1$/,
    /^Delphine Arkwright\s*1 boon · weight 1$/,
    /^Edmund Reyes\s*1 boon · weight 1$/,
    /^Fenella Grist\s*1 boon · weight 1$/,
    /^Gideon Hart\s*2 boons · weight 2$/,
  ]);
  await expect(heading("Aldric Vane 2 boons · weight 4")).toHaveAttribute("aria-expanded", "true");
  await expect(heading("Fenella Grist 1 boon · weight 1")).toHaveAttribute("aria-expanded", "false");
  await expect(boons.rows).toHaveCount(6);
  await expect(boons.row("Aldric Vane owes Isaura Penhallow, major")).toHaveCount(1);
  await expect(boons.row("Gideon Hart owes Isaura Penhallow, minor")).toHaveCount(0);
  // A closed group opens from its heading, and an open one closes.
  await heading("Gideon Hart 2 boons · weight 2").click();
  await expect(boons.row("Gideon Hart owes Isaura Penhallow, minor")).toHaveCount(2);
  await heading("Aldric Vane 2 boons · weight 4").click();
  await expect(boons.row("Aldric Vane owes Isaura Penhallow, major")).toHaveCount(0);
  await expect(boons.rows).toHaveCount(6);
  // A row in a group opens as any row does.
  await boons.open("Beatrix Moll owes Isaura Penhallow, minor");
  await expect(boons.detail("Beatrix Moll owes Isaura Penhallow, minor")).toBeVisible();
  await boons.close();
  // Nothing sideways on a phone.
  expect(await l.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  await l.screenshot(shots("boon-ledger-grouped"));

  // A reload keeps the grouping; there is no pager, every row is there.
  await l.reload();
  await expect(headings).toHaveCount(7);
  await expect(groupBy).toHaveValue("debtor");
  await expect(pages).toHaveCount(0);
  // By creditor, one group; by night, newest first.
  await groupBy.selectOption({ label: "Creditor" });
  await expect(headings).toHaveText([/^Isaura Penhallow\s*9 boons · weight 11$/]);
  await expect(boons.rows).toHaveCount(9);
  await groupBy.selectOption({ label: "Night" });
  await expect(headings).toHaveText([/^7 March 2026\s*4 boons · weight 6$/, /^7 February 2026\s*4 boons · weight 4$/, /^3 January 2026\s*1 boon · weight 1$/]);

  // Trivial only: 500, as many as can be grouped, read at once past the first page.
  await groupBy.selectOption({ label: "Debtor" });
  await kinds.getByRole("button", { name: "Minor" }).click();
  await kinds.getByRole("button", { name: "Major" }).click();
  await kinds.getByRole("button", { name: "Trivial" }).click();
  await expect(headings).toHaveText([/^Ledger filler\s*500 boons · weight 250$/]);
  await expect(boons.rows).toHaveCount(500);

  // Every boon again: 509, too many; the pages come back, the choice kept for a narrower search.
  await l.getByRole("button", { name: "Show every boon" }).click();
  await expect(groupBy).toBeDisabled();
  await expect(groupBy).toHaveValue("");
  await expect(headings).toHaveCount(0);
  await expect(pages).toContainText("1 to 100 of 509");
  await expect(boons.rows).toHaveCount(100);
  await expect(l).toHaveURL(/[?&]group=debtor\b/);
});

test("a name on a boon goes to their own page: what they owe and are owed, totalled as the standings count them, with ways to audit them and to their sheet (#980)", async ({ browser }) => {
  const custodian = await person(browser, "bparty-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bparty-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Own Pages ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  const ottoline = await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Ottoline Brascombe" });
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  const owes = (debtor: object, creditor: object, kind: string, made_on: string) => ({ debtor, creditor, kind, made_on, reason: "" });
  const her = { character_id: ottoline.id };
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [
      owes(her, { name: "Gaspard Lindqvist" }, "minor", "2026-03-01"),
      owes(her, { name: "Gaspard Lindqvist" }, "trivial", "2026-04-01"),
      owes({ name: "Perpetua Quill" }, her, "major", "2026-05-01"),
      owes({ name: "Gaspard Lindqvist" }, { name: "Perpetua Quill" }, "life", "2026-06-01"),
    ],
    note: "",
  });

  // Her name in the table goes to her page; on a phone, where a tap opens the row, her name in the boon's detail does.
  await l.goto(`/troupes/${troupe.id}/boons`);
  const boons = ledgerOf(l);
  await expect(boons.rows).toHaveCount(4);
  if (onPhone()) {
    await boons.open("Perpetua Quill owes Ottoline Brascombe, major");
    await boons.detail("Perpetua Quill owes Ottoline Brascombe, major").getByRole("link", { name: "Ottoline Brascombe" }).click();
    await expect(l.locator("dialog[open]")).toHaveCount(0);
  } else {
    await boons.row("Perpetua Quill owes Ottoline Brascombe, major").getByRole("link", { name: "Ottoline Brascombe" }).click();
  }
  await expect(l).toHaveURL(new RegExp(`[?&]character=${ottoline.id}`));
  const head = l.getByRole("region", { name: "Whose boons" });
  await expect(head.getByRole("heading", { name: "Ottoline Brascombe" })).toBeVisible();
  // By the troupe's weights: minor 1 and trivial 0.5 owed by her, a major (3) to her.
  await expect(head).toContainText("Owes 2 (weight 1.5) · Is owed 1 (weight 3)");
  const owesList = l.getByRole("table", { name: "Owes", exact: true });
  const owedList = l.getByRole("table", { name: "Is owed", exact: true });
  await expect(owesList.getByRole("button", { name: /^Details: / })).toHaveCount(2);
  await expect(owedList.getByRole("button", { name: /^Details: / })).toHaveCount(1);
  await expect(owedList.getByRole("row", { name: "Perpetua Quill owes Ottoline Brascombe, major" })).toHaveCount(1);
  // Each section names only the other side.
  if (!onPhone()) {
    await expect(owesList.getByRole("columnheader", { name: "Debtor" })).toHaveCount(0);
    await expect(owesList.getByRole("columnheader", { name: "Creditor" })).toHaveCount(1);
    await expect(owedList.getByRole("columnheader", { name: "Debtor" })).toHaveCount(1);
  }
  // The kinds narrow both sections; the totals stay.
  await l.getByRole("group", { name: "Kinds" }).getByRole("button", { name: "Major" }).click();
  await expect(owesList).toHaveCount(0);
  await expect(l.getByRole("region", { name: /^Owes/ })).toContainText("No boons match.");
  await expect(owedList.getByRole("button", { name: /^Details: / })).toHaveCount(1);
  await expect(head).toContainText("Owes 2 (weight 1.5) · Is owed 1 (weight 3)");
  await l.getByRole("group", { name: "Kinds" }).getByRole("button", { name: "Major" }).click();
  await l.screenshot(shots("boon-party"));

  // For staff, her sheet; and an audit of her, from the Audits tab, with her picked.
  await expect(head.getByRole("link", { name: "Character sheet" })).toHaveAttribute("href", `/characters/${ottoline.id}`);
  await head.getByRole("link", { name: "Make an audit" }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupe.id}/boons/audits\\?character=${ottoline.id}$`));
  await expect(l.getByLabel("Audit", { exact: true })).toHaveValue(ottoline.id);

  // A name only works the same, matched on the whole name, any case: no sheet, no audit.
  await l.goto(`/troupes/${troupe.id}/boons?name=gaspard+lindqvist`);
  await expect(head.getByRole("heading", { name: "Gaspard Lindqvist" })).toBeVisible();
  await expect(head).toContainText("(name only)");
  await expect(head).toContainText("Owes 1 (weight 10) · Is owed 2 (weight 1.5)");
  await expect(head.getByRole("link")).toHaveCount(1);
  // Back to the whole ledger.
  await head.getByRole("link", { name: "The whole ledger" }).click();
  await expect(boons.rows).toHaveCount(4);
  await expect(l).not.toHaveURL(/name=/);
});

test("staff write a passage of story on a side of a boon, cut to a line, and its other side's player reads it as written (#990)", async ({ browser }) => {
  const custodian = await person(browser, "boonstory-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "boonstory-lead");
  const player = await person(browser, "boonstory-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Debts in Story ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const lisette = await builtVampire(player.page, "Lisette Crane", "Brujah", build);
  const asked = await send(player.page, "POST", `/api/characters/${lisette}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-players`, { see: "owed", settle: false });
  // 600 characters of the plot where the debtor's name would be.
  const story = "The debt was written in silver on the night the river froze, and sealed. ".repeat(9).slice(0, 600).trim();

  // The lead registers it, with the ledger narrowed to trivial boons: the picker's last choice is someone not in
  // Horatio, which takes any text.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/boons?kind=trivial`);
  await l.getByRole("button", { name: "Register boons" }).click();
  const entry = l.getByRole("dialog", { name: "Register boons" }).getByRole("form", { name: "Register boons" });
  const row = entry.getByRole("listitem", { name: "Boon 1" });
  await row.getByRole("combobox", { name: "Debtor" }).click();
  await row.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: "Someone not in Horatio…" }).click();
  const text = row.getByRole("textbox", { name: "Debtor" });
  await expect(text).toBeFocused();
  await expect(text).toHaveAttribute("maxlength", "2000");
  await expect(row.getByText("Its other side's player sees this as written.")).toBeVisible();
  await text.fill(story);
  await row.getByRole("combobox", { name: "Creditor" }).fill("Lisette");
  await row.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Lisette Crane/ }).click();
  await row.getByLabel("Reason").fill("Passage across the frozen river");
  await entry.getByRole("button", { name: "Register the boon" }).click();
  await expect(l.getByText("Registered a boon.")).toBeVisible();
  // A minor boon, which the filter hides (#983): the toast shows it, clearing the filter.
  await expect(entry).toBeHidden();
  await l.getByRole("button", { name: "Show it" }).click();
  await expect(l).not.toHaveURL(/kind=/);

  // In the ledger, one line, in italics as a name only, all of it on hover (#975); its detail has it in full, and
  // opened to edit, it is there to change.
  const line = ledgerOf(l).table.getByRole("row", { name: /^The debt was written in silver/ });
  await expect(line).toHaveCount(1);
  await expect(line.locator(`[title="${story}"]`).filter({ visible: true }).first()).toHaveCSS("font-style", "italic");
  await line.click();
  const detail = l.getByRole("region", { name: /^Boon: The debt was written in silver/ });
  await expect(detail.getByText(story, { exact: true })).toBeVisible();
  await l.getByRole("button", { name: /^Actions: The debt was written in silver/ }).click();
  await l.getByRole("menuitem", { name: "Edit", exact: true }).click();
  await expect(detail.getByRole("textbox", { name: "Debtor" })).toHaveValue(story);
  await detail.getByRole("button", { name: "Cancel" }).click();

  // Lisette's player reads it as written: a line of it, and all of it under "more".
  const p = player.page;
  await p.goto(`/play/characters/${lisette}?tab=boons`);
  const owed = p.getByRole("region", { name: "Owed to Lisette Crane" }).getByRole("listitem").filter({ hasText: "Passage across the frozen river" });
  await expect(owed).toContainText(story.slice(0, 40));
  const more = owed.getByRole("button", { name: /^Read all of/ });
  await more.click();
  await expect(p.locator(`[id="${await more.getAttribute("aria-controls")}"]`)).toHaveText(story);
});

test("staff export the ledger from its ⋯ menu: this view or the whole ledger, as a CSV file or a spreadsheet, or a workbook (#986, #988)", async ({ browser }) => {
  const custodian = await person(browser, "bexport-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bexport-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Debts Exported ${run}`, lead_handle: lead.handle });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  // Names only on either side, and a reason a spreadsheet would run as a formula.
  const boon = (debtor: string, creditor: string, kind: string, reason: string) => ({ debtor: { name: debtor }, creditor: { name: creditor }, kind, made_on: "2026-10-03", reason });
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [boon("Odile Marchand", "Rufus Kett", "major", "=2+2"), boon("Rufus Kett", "Odile Marchand", "minor", "Directions")],
  });

  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}`);
  await troupeTab(l, "Boons");
  const ledger = ledgerOf(l);
  await expect(ledger.rows).toHaveCount(2);
  await l.getByRole("group", { name: "Kinds" }).getByRole("button", { name: "Major" }).click();
  await expect(ledger.rows).toHaveCount(1);

  const { readFile } = await import("node:fs/promises");
  const exported = async (item: string) => {
    await l.getByRole("button", { name: "More for the ledger" }).click();
    const downloading = l.waitForEvent("download");
    await l.getByRole("menuitem", { name: item }).click();
    return downloading;
  };
  // This view: the major boon only, its formula kept as text, in a file Excel reads as UTF-8.
  const view = await exported("This view (CSV)");
  expect(view.suggestedFilename()).toMatch(/^debts-exported-.*-boons-\d{4}-\d{2}-\d{2}\.csv$/);
  const csv = (await readFile(await view.path(), "utf8")).trimEnd().split("\r\n");
  expect(csv[0]).toMatch(/^\uFEFFOwed By,Owed To,Type,Date,Reason,Stipulation,State,/);
  expect(csv).toHaveLength(2);
  expect(csv[1]).toMatch(/^Odile Marchand,Rufus Kett,Major,2026-10-03,'=2\+2,,Standing,No,/);

  // The whole ledger, as a spreadsheet.
  const whole = await exported("Whole ledger (spreadsheet)");
  expect(whole.suggestedFilename()).toMatch(/-boons-\d{4}-\d{2}-\d{2}\.xlsx$/);
  const book = await readFile(await whole.path());
  expect(book.subarray(0, 2).toString()).toBe("PK");

  // The whole ledger as a workbook shaped like the old sheet (#988).
  const workbook = await exported("Whole ledger as a workbook");
  expect(workbook.suggestedFilename()).toMatch(/^debts-exported-.*-boon-ledger-\d{4}-\d{2}-\d{2}\.xlsx$/);
  expect((await readFile(await workbook.path())).subarray(0, 2).toString()).toBe("PK");

  // Each export is in the troupe's log.
  const log = await (await l.request.get(`/api/troupes/${troupe.id}/log`)).json();
  const messages = log.map((e: { message: string }) => e.message);
  expect(messages).toContain("bexport-lead exported part of the boon ledger as a CSV file (1 boon).");
  expect(messages).toContain("bexport-lead exported the whole boon ledger as a spreadsheet (2 boons).");
  expect(messages).toContain("bexport-lead exported the whole boon ledger as a workbook (2 boons).");
});

test("where the troupe lets them, the Harpy exports the ledger as they see it, and lets a Lesser Harpy export it too (#987)", async ({ browser }) => {
  const custodian = await person(browser, "hexport-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "hexport-lead");
  const harpy = await person(browser, "hexport-harpy");
  const talon = await person(browser, "hexport-talon");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Close Accounts ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const sabine = await home(harpy.page, "Sabine Lorne");
  const teodor = await home(talon.page, "Teodor Vasz");
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-harpy`, { access: "full" });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-talons-setting`, { on: true, word: "Lesser Harpies" });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/characters/${sabine}/titles`, { titles: ["Harpy"] });
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [{ debtor: { character_id: teodor }, creditor: { name: "Ysolde Marr" }, kind: "major", made_on: "2026-10-03", reason: "Safe haven", staff_note: "Ysolde's player is new" }],
  });

  // Off to begin with: the Harpy's ledger has no ⋯ to export from.
  const h = harpy.page;
  await h.goto(`/play/characters/${sabine}/ledger`);
  await expect(ledgerOf(h).rows).toHaveCount(1);
  await expect(h.getByRole("button", { name: "More for the ledger" })).toHaveCount(0);

  // The lead lets the Harpy export.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/boons#settings`);
  const lets = (await tabSettings(l, "Boons")).getByRole("switch", { name: /^The Harpy may export the ledger/ });
  await lets.click();
  await expect(l.getByText("Saved: the Harpy may export the ledger.")).toBeVisible();
  await expect(lets).toBeChecked();

  // Sabine's player downloads the whole ledger: no staff's columns, no staff note.
  const { readFile } = await import("node:fs/promises");
  const exported = async (page: Page) => {
    await page.getByRole("button", { name: "More for the ledger" }).click();
    const downloading = page.waitForEvent("download");
    await page.getByRole("menuitem", { name: "Whole ledger (CSV)" }).click();
    return (await readFile(await (await downloading).path(), "utf8")).trimEnd().split("\r\n");
  };
  await h.reload();
  const csv = await exported(h);
  expect(csv[0]).toMatch(/^\uFEFFOwed By,Owed To,Type,Date,Reason,Stipulation,State,.*,Registered,ID$/);
  expect(csv[0]).not.toContain("Staff Note");
  expect(csv).toHaveLength(2);
  expect(csv[1]).toMatch(/^Teodor Vasz,Ysolde Marr,Major,2026-10-03,Safe haven,/);
  expect(csv.join("\n")).not.toContain("Ysolde's player is new");

  // She makes Teodor a Lesser Harpy who may export it too.
  await h.getByLabel("Make a Lesser Harpy").selectOption({ label: "Teodor Vasz" });
  const may = h.getByRole("group", { name: "What they may do" });
  await may.getByRole("checkbox", { name: "Export the ledger" }).check();
  await h.getByRole("button", { name: "Give access" }).click();
  await expect(h.getByText("Teodor Vasz has access to the ledger.")).toBeVisible();
  const t = talon.page;
  await t.goto(`/play/characters/${teodor}/ledger`);
  expect(await exported(t)).toHaveLength(2);

  // Each export is in the troupe's log, with the character it was done as.
  const log = await (await l.request.get(`/api/troupes/${troupe.id}/log`)).json();
  const messages = log.map((e: { message: string }) => e.message);
  expect(messages).toContain("hexport-harpy as Sabine Lorne exported the whole boon ledger as a CSV file (1 boon).");
  expect(messages).toContain("hexport-talon as Teodor Vasz exported the whole boon ledger as a CSV file (1 boon).");
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

  // Under Court › Boons, Standings: Casimir is owed a major and owes a minor.
  await l.goto(`/troupes/${troupe.id}`);
  await troupeTab(l, "Boons");
  await l.getByRole("navigation", { name: "Boons", exact: true }).getByRole("link", { name: "Standings", exact: true }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupe.id}/boons/standings$`));
  const standing = l.getByRole("table", { name: "Standing by character" });
  await expect(standing.getByRole("row", { name: /Casimir Wode/ })).toContainText("+2");
  await expect(standing.getByRole("row", { name: /Isolde Fenwright/ })).toContainText("−2");
  await expect(l.getByRole("table", { name: "Owing each other" })).toContainText("Isolde Fenwright");
  // Each total says what it counts, under its number (#919).
  await expect(l.getByRole("definition").filter({ hasText: "Standing, with everyone on them in play." })).toBeVisible();

  // The troupe weighs a major boon at 4: the sums follow.
  await l.getByRole("button", { name: "Edit the weights" }).click();
  await l.getByLabel("Major").fill("4");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("The boon weights are saved.")).toBeVisible();
  await expect(standing.getByRole("row", { name: /Casimir Wode/ })).toContainText("+3");
  await expect(l.getByText(/Major 4/)).toBeVisible();
});

test("on a phone the boon standings fold into blocks, nothing sideways with 20 long names; from sm up they are tables (#914)", async ({ browser }) => {
  const custodian = await person(browser, "bfold914-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bfold914-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Ledger of Long Names ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  const names = Array.from({ length: 20 }, (_, i) =>
    i === 0 ? "Wolfeschlegelsteinhausenbergerdorffvoralternwarengewissenhaft" : `Bartholomew Featherstonehaugh-Cholmondeley of Wolverhampton ${i + 1}`,
  );
  const npcs: { id: string }[] = [];
  for (const name of names) npcs.push(await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, { name }));
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  // Each owes the next a major boon, and the first two owe each other.
  const owes = (debtor: { id: string }, creditor: { id: string }, kind: string) => ({ debtor: { character_id: debtor.id }, creditor: { character_id: creditor.id }, kind, made_on: "2026-10-03" });
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, { boons: [...npcs.map((n, i) => owes(n, npcs[(i + 1) % 20], "major")), owes(npcs[1], npcs[0], "minor")] });

  const phone = test.info().project.name === "phone";
  if (phone) await l.setViewportSize({ width: 375, height: 800 });
  await l.goto(`/troupes/${troupe.id}/boons/standings`);
  const standing = l.getByRole("table", { name: "Standing by character" });
  await expect(standing.locator("tbody tr")).toHaveCount(20);
  await expect(standing.getByText(names[0], { exact: true })).toBeVisible();
  await expect(l.getByRole("table", { name: "Owing each other" })).toContainText(names[0]);
  // Against the viewport, not innerWidth: a phone widens its layout to fit what is too wide.
  expect(await l.evaluate(() => document.documentElement.scrollWidth)).toBe(l.viewportSize()!.width);
  // The net, under the name on a phone and in its column from sm up, both read in words.
  const first = standing.getByRole("row", { name: new RegExp(names[0]) });
  await expect(first).toContainText("+1");
  if (phone) await expect(first.getByText("Net:", { exact: true })).toBeVisible();
  else {
    await expect(standing.getByRole("columnheader", { name: "Net" })).toBeVisible();
    await expect(first.getByRole("cell", { name: "owed 1 more than they owe" })).toBeVisible();
  }
  await l.screenshot(shots("boon-standings-long-names"));
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
  const boons = ledgerOf(l);
  await expect(boons.row("Maelis Thorne owes Corvin Ashgrave, minor")).toContainText("Disgraced");
  await boons.row("Maelis Thorne owes Corvin Ashgrave, minor").click();
  await expect(boons.detail("Maelis Thorne owes Corvin Ashgrave, minor")).toContainText("Need not be repaid while Corvin Ashgrave is Disgraced (p. 316).");

  // On Corvin's status, staff register the major boon his apology owes the Prince.
  await l.goto(`/characters/${corvin}/status`);
  const card = l.locator("section").filter({ has: l.getByRole("heading", { name: "Status", exact: true }) });
  await card.getByRole("listitem", { name: "Disgraced" }).getByRole("button", { name: "Apology boon…" }).click();
  const form = card.getByRole("form", { name: "Apology boon for a slip while Disgraced" });
  await expect(form.getByLabel("Owed to: whoever was wronged")).toHaveValue("Prince Aurelian");
  await form.getByRole("button", { name: "Register a major boon" }).click();
  await expect(l.getByText("Registered a major boon owed by Corvin Ashgrave.")).toBeVisible();
  await l.goto(`/troupes/${troupe.id}/boons`);
  await expect(boons.row("Corvin Ashgrave owes Prince Aurelian, major")).toContainText("An apology for a slip while Disgraced");
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

  // The old address of Boon statistics, from before it joined Boons (#780), still leads there.
  await l.goto(`/troupes/${troupe.id}/boon-statistics`);
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupe.id}/boons/statistics$`));
  // Under Court › Boons, Statistics: each of the four charts, every one with its table.
  await l.goto(`/troupes/${troupe.id}`);
  await troupeTab(l, "Boons");
  await l.getByRole("navigation", { name: "Boons", exact: true }).getByRole("link", { name: "Statistics", exact: true }).click();
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
  await l.goto(`/troupes/${troupe.id}/boons#settings`);
  await tabSettings(l, "Boons");
  await l.getByRole("radio", { name: /^Also what they're owed/ }).check();
  await expect(l.getByText("Saved what players see of the boon ledger.")).toBeVisible();
  await l.getByRole("switch", { name: /^Players mark boons owed to them settled/ }).check();
  await expect(l.getByRole("switch", { name: /^Players mark boons owed to them settled/ })).toBeChecked();

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
  // With the day it was settled, a date and not NaN (#998).
  await expect(owed.getByRole("listitem", { name: "Major boon from Tobiah Venn" })).toContainText(/Settled: forgiven, \d{1,2} [A-Z][a-z]{2} \d{4}\. For old times\./);

  // In the ledger, staff see it was done as Isolde.
  await l.goto(`/troupes/${troupe.id}/boons`);
  await showView(l, "settled");
  await ledgerOf(l).row("Tobiah Venn owes Isolde Marrow, major").click();
  const log = ledgerOf(l).detail("Tobiah Venn owes Isolde Marrow, major").getByRole("list", { name: "Log of Tobiah Venn owes Isolde Marrow" });
  await expect(log).toContainText("as Isolde Marrow");
  await expect(log).toContainText("For old times");
});

test("a creditor with Social Nobility, repaid a boon, gives its debtor Gallant from the Play View (#693)", async ({ browser }) => {
  const custodian = await person(browser, "gallant-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "gallant-lead");
  const creditor = await person(browser, "gallant-creditor");
  const debtor = await person(browser, "gallant-debtor");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "GET" | "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, ...(method === "GET" ? {} : { data }) });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Repaid in Full ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  // Two Camarilla Brujah, built through the API and accepted home: Corvane has Social Nobility.
  const home = async (page: Page, name: string, merits: [string, number][]) => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const build: Record<string, [string, number][]> = {
      ...ATTRIBUTES_AND_FOCUSES,
      backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
      disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
      ...(merits.length ? { merits } : {}),
    };
    for (const [category, picks] of Object.entries(build))
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([n, rating]) => ({ name: n, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`);
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id as string;
  };
  const corvane = await home(creditor.page, "Lady Corvane", [["Social Nobility", 3]]);
  const hesk = await home(debtor.page, "Hesk Arlow", []);
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-players`, { see: "owed", settle: true });
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [{ debtor: { character_id: hesk }, creditor: { character_id: corvane }, kind: "minor", made_on: "2026-10-03", reason: "A word with the Prince" }],
    note: "",
  });

  // Corvane's player calls the boon in, and is offered Gallant for Hesk.
  const c = creditor.page;
  await c.goto(`/play/characters/${corvane}?tab=boons`);
  const owed = c.getByRole("region", { name: "Owed to Lady Corvane" });
  const held = owed.getByRole("listitem", { name: "Minor boon from Hesk Arlow" });
  await held.getByRole("button", { name: "Settle" }).click();
  const settle = held.getByRole("form", { name: "Settle the boon" });
  await settle.getByLabel(/^Called in/).check();
  await settle.getByRole("button", { name: "Mark it settled" }).click();
  await owed.getByText("Settled (1)").click();
  const repaid = owed.getByRole("listitem", { name: "Minor boon from Hesk Arlow" });
  const offer = repaid.getByRole("group", { name: "Gallant offered" });
  await expect(offer).toContainText("Give Hesk Arlow Gallant for repaying it? The creditor has Social Nobility (p. 405).");
  await offer.getByRole("button", { name: "Give Gallant" }).click();
  await expect(offer).toHaveCount(0);

  // Hesk holds Gallant, from Corvane; the boon's log says it was given, as Corvane.
  const found = await send(debtor.page, "GET", `/api/characters/${hesk}/status`);
  expect(found.held.map((h: { name: string }) => h.name)).toEqual(["Gallant"]);
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/boons`);
  await showView(l, "settled");
  await ledgerOf(l).row("Hesk Arlow owes Lady Corvane, minor").click();
  const log = ledgerOf(l).detail("Hesk Arlow owes Lady Corvane, minor").getByRole("list", { name: "Log of Hesk Arlow owes Lady Corvane" });
  await expect(log).toContainText("Gallant given");
  await expect(log).toContainText("as Lady Corvane");
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
  await l.goto(`/troupes/${troupe.id}/boons#settings`);
  const hold = (await tabSettings(l, "Boons")).getByRole("switch", { name: /^Boons players report wait for review/ });
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
  // The troupe gives its Harpy no access, so staff approve it (#993).
  await expect(p.getByText("Waiting for staff's approval: Mysterious Stranger owes Corvin Ashby a minor boon.")).toBeVisible();
  const reports = tab.getByRole("list", { name: "Your reports" });
  await expect(reports).toContainText("Mysterious Stranger owes Corvin Ashby a minor boon");
  await expect(reports).toContainText("Waiting for staff's approval.");

  // The lead sees it waiting for approval, flagged for its name, opens it from its row and accepts it with a note.
  await l.goto(`/troupes/${troupe.id}/boons`);
  await boonTab(l, "To review").click();
  const waiting = l.getByRole("table", { name: "Waiting for approval" });
  const row = waiting.getByRole("row", { name: "Mysterious Stranger owes Corvin Ashby, minor" });
  await expect(row.getByText("Flagged").filter({ visible: true })).toBeVisible();
  await row.getByRole("button", { name: "Details: Mysterious Stranger owes Corvin Ashby, minor" }).click();
  const review = waiting.getByRole("group", { name: "Review" });
  await expect(review).toContainText("Mysterious Stranger: No character in the troupe has this name.");
  await review.getByRole("button", { name: "Accept", exact: true }).click();
  const accept = review.getByRole("form", { name: "Accept: Mysterious Stranger owes Corvin Ashby" });
  await accept.getByLabel("Note (optional)").fill("Confirmed with the Harpy");
  await accept.getByRole("button", { name: "Accept it" }).click();
  await expect(l.getByText("Accepted: Mysterious Stranger owes Corvin Ashby.")).toBeVisible();
  // The troupe holds reports for review, so the tab stays, and says nothing waits.
  await expect(l.getByText("Nothing waits for approval.")).toBeVisible();
  await expect(boonTab(l, "To review")).toHaveAccessibleName("To review");

  // It stands in the ledger, with its review in its log; and the report is gone from the player's tab.
  await boonTab(l, "Ledger").click();
  await ledgerOf(l).row("Mysterious Stranger owes Corvin Ashby, minor").click();
  const log = ledgerOf(l).detail("Mysterious Stranger owes Corvin Ashby, minor").getByRole("list", { name: "Log of Mysterious Stranger owes Corvin Ashby" });
  await expect(log).toContainText("Reported for review");
  await expect(log).toContainText("Accepted");
  await expect(log).toContainText("Confirmed with the Harpy");
  // The player's report says it's in the ledger now (#993).
  await p.reload();
  await expect(p.getByRole("region", { name: "Boons" }).getByRole("form", { name: "Report a boon" })).toBeVisible();
  await expect(p.getByRole("list", { name: "Your reports" })).toContainText("In the ledger.");
});

test("the Harpy approves reported boons: a ticked kind goes straight in, the rest wait, accepted or not from their rows (#993)", async ({ browser }) => {
  const custodian = await person(browser, "bappr-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bappr-lead");
  const harpy = await person(browser, "bappr-harpy");
  const player = await person(browser, "bappr-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Debts Approved ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const seraphine = await home(harpy.page, "Seraphine Vey");
  const lucan = await home(player.page, "Lucan Marsh");
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-review`, { hold: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-harpy`, { access: "submissions" });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/characters/${seraphine}/titles`, { titles: ["Harpy"] });

  // The Harpy lets trivial boons go straight in, from Approval settings on the queue.
  const h = harpy.page;
  await h.goto(`/play/characters/${seraphine}/ledger`);
  await expect(h.getByText("Every boon players report waits for approval.")).toBeVisible();
  await h.getByRole("button", { name: "Approval settings" }).click();
  const settings = h.getByRole("dialog", { name: "Approval settings" });
  await settings.getByRole("checkbox", { name: "Trivial" }).check();
  await settings.getByRole("button", { name: "Save" }).click();
  await expect(h.getByText("Saved. Trivial boons players report go straight into the ledger; the rest wait.")).toBeVisible();
  await expect(settings).toBeHidden();

  // Lucan's player reports a trivial boon and two major ones: the trivial one is in the ledger, the others wait for the Harpy.
  const p = player.page;
  await p.goto(`/play/characters/${lucan}?tab=boons`);
  const tab = p.getByRole("region", { name: "Boons" });
  const report = tab.getByRole("form", { name: "Report a boon" });
  await report.getByLabel("Who").selectOption({ label: "Seraphine Vey" });
  await report.getByLabel("Kind").selectOption("trivial");
  await report.getByLabel("Reason").fill("A word in the right ear");
  await report.getByRole("button", { name: "Report the boon" }).click();
  await expect(p.getByText(`Reported to Debts Approved ${run}'s ledger: Lucan Marsh owes Seraphine Vey a trivial boon.`)).toBeVisible();
  const reported = (kind: string, reason: string) =>
    send(p, "POST", `/api/characters/${lucan}/play-boons`, { other: { character_id: seraphine }, direction: "owed", kind, made_on: "2026-10-03", reason });
  await reported("major", "Safe passage");
  await reported("major", "A secret kept");
  await p.reload();
  const reports = p.getByRole("list", { name: "Your reports" });
  await expect(reports.getByRole("listitem").filter({ hasText: "A word in the right ear" })).toContainText("In the ledger.");
  await expect(reports.getByRole("listitem").filter({ hasText: "Safe passage" })).toContainText("Waiting for the Harpy's approval.");

  // The Harpy doesn't accept one, from its row, with why; then narrows the rest to major boons and accepts all shown.
  await h.reload();
  const waiting = h.getByRole("table", { name: "Waiting for approval" });
  await expect(waiting.getByRole("row", { name: "Seraphine Vey owes Lucan Marsh, major" })).toHaveCount(2);
  await expect(waiting).not.toContainText("A word in the right ear");
  await h.screenshot(shots("harpy-approval"));
  await waiting.getByRole("button", { name: "Don't accept: Seraphine Vey owes Lucan Marsh" }).first().click();
  const refuse = h.getByRole("dialog", { name: "Don't accept: Seraphine Vey owes Lucan Marsh" });
  await refuse.getByLabel("Why").fill("No one saw it struck");
  await refuse.getByRole("button", { name: "Don't accept it" }).click();
  await expect(h.getByText("Not accepted: Seraphine Vey owes Lucan Marsh.")).toBeVisible();
  await expect(waiting.getByRole("row", { name: "Seraphine Vey owes Lucan Marsh, major" })).toHaveCount(1);
  await h.getByRole("group", { name: "Narrow the boons waiting" }).getByLabel("Kind").selectOption("major");
  await h.getByRole("button", { name: "Accept all shown (1)" }).click();
  await h.getByRole("dialog", { name: "Accept 1 boon?" }).getByRole("button", { name: "Accept them" }).click();
  await expect(h.getByText("Accepted 1 boon.")).toBeVisible();
  await expect(h.getByText("Nothing waits for approval.")).toBeVisible();

  // The player reads what happened to each.
  await p.reload();
  await expect(reports.getByText("Not accepted", { exact: false })).toContainText("No one saw it struck");
  await expect(reports.getByText("In the ledger.")).toHaveCount(2);
});

test("staff choose to be told when a player reports a boon, and the Harpy, told from the start, may stop it (#1018)", async ({ browser }) => {
  const custodian = await person(browser, "btold-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "btold-lead");
  const harpy = await person(browser, "btold-harpy");
  const player = await person(browser, "btold-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Debts Heralded ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const marguerite = await home(harpy.page, "Marguerite Sallow");
  const tobias = await home(player.page, "Tobias Wren");
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-review`, { hold: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-harpy`, { access: "full" });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/characters/${marguerite}/titles`, { titles: ["Harpy"] });

  // The lead asks to be told, just for them, in the Boons settings: off to begin with.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/boons#settings`);
  const settings = await tabSettings(l, "Boons");
  const mine = settings.getByRole("switch", { name: "Tell me when a player reports a boon" });
  await expect(mine).not.toBeChecked();
  await mine.check();
  await expect(l.getByText("You'll be told when a player reports a boon.")).toBeVisible();
  await expect(mine).toBeChecked();
  await l.screenshot(shots("boon-reports-told-staff"));

  // The Harpy is told from the start, and turns it off on their ledger's To review tab.
  const h = harpy.page;
  await h.goto(`/play/characters/${marguerite}/ledger/review`);
  const theirs = h.getByRole("switch", { name: "Tell me when a player reports a boon" });
  await expect(theirs).toBeChecked();
  await h.screenshot(shots("boon-reports-told-harpy"));
  await theirs.uncheck();
  await expect(h.getByText("You won't be told when a player reports a boon.")).toBeVisible();
  await expect(theirs).not.toBeChecked();

  // Account › Notifications shows each of those choices, kept in one place (#1053): a
  // change there is the change beside the role.
  await l.goto("/account/notifications#boons");
  await expect(l.getByRole("switch", { name: `Debts Heralded ${run}: as staff` })).toBeChecked();
  await h.goto("/account/notifications#boons");
  const listed = h.getByRole("switch", { name: `Debts Heralded ${run}: as Harpy, Marguerite Sallow` });
  await expect(listed).not.toBeChecked();
  await listed.check();
  await expect(h.getByText("You'll be told when a player reports a boon.")).toBeVisible();
  await h.screenshot(shots("boon-reports-told-notifications"));
  await h.goto(`/play/characters/${marguerite}/ledger/review`);
  await expect(theirs).toBeChecked();
  await theirs.uncheck();
  await expect(theirs).not.toBeChecked();

  // Tobias's player reports a boon; the lead is told, and the word opens To review.
  await send(player.page, "POST", `/api/characters/${tobias}/play-boons`, {
    other: { character_id: marguerite },
    direction: "owes",
    kind: "minor",
    made_on: "2026-10-03",
    reason: "A door left unlocked",
  });
  await l.goto(`/troupes/${troupe.id}`);
  await l.getByRole("button", { name: /^Notifications, \d+ waiting$/ }).click();
  await l.getByRole("button", { name: /Tobias Wren reported a minor boon to the ledger: Tobias Wren owes Marguerite Sallow/ }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupe.id}/boons/review$`));
  await expect(l.getByRole("table", { name: "Waiting for approval" }).getByRole("row", { name: "Tobias Wren owes Marguerite Sallow, minor" })).toBeVisible();

  // The Harpy, who turned it off, isn't.
  const word = await (await h.request.get("/api/notifications")).json();
  expect(word.items.filter((n: { kind: string }) => n.kind === "boon.reported")).toEqual([]);
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
  const edric = await home(player.page, "Edric Thorne");
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/characters/${philippa}/titles`, { titles: ["Harpy"] });

  // The lead gives the Harpy the full ledger.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/boons#settings`);
  const full = (await tabSettings(l, "Boons")).getByRole("radio", { name: /^The full ledger/ });
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
  // Two rows at once, in the dialog (#983).
  await h.getByRole("button", { name: "Register boons" }).click();
  const dialog = h.getByRole("dialog", { name: "Register boons" });
  const entry = dialog.getByRole("form", { name: "Register boons" });
  await entry.getByLabel("Date for new rows").fill("2026-10-03");
  const row = entry.getByRole("listitem", { name: "Boon 1" });
  await row.getByRole("combobox", { name: "Debtor" }).fill("Edric");
  await row.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Edric Thorne/ }).click();
  await row.getByRole("combobox", { name: "Creditor" }).fill("Lady Ashgrove");
  await row.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /name only/ }).click();
  await row.getByLabel("Reason").fill("Safe passage");
  await entry.getByRole("button", { name: "Add a row" }).click();
  const another = entry.getByRole("listitem", { name: "Boon 2" });
  await another.getByRole("combobox", { name: "Debtor" }).fill("Edric");
  await another.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Edric Thorne/ }).click();
  await another.getByRole("combobox", { name: "Creditor" }).fill("Philippa");
  await another.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Philippa Quill/ }).click();
  await another.getByLabel("Kind").selectOption("trivial");
  await another.getByLabel("Reason").fill("A word at Elysium");
  await entry.getByRole("button", { name: "Register 2 boons" }).click();
  await expect(h.getByText("Registered 2 boons.")).toBeVisible();
  await expect(dialog).toBeHidden();
  await expect(ledgerOf(h).row("Edric Thorne owes Philippa Quill, trivial")).toBeVisible();

  // She corrects it, with a note: her log shows the edit as hers, not what it changed.
  const boons = ledgerOf(h);
  await boons.open("Edric Thorne owes Lady Ashgrove, minor");
  const debt = boons.detail("Edric Thorne owes Lady Ashgrove, minor");
  await boons.act("Edric Thorne owes Lady Ashgrove, minor", "Edit");
  const edit = debt.getByRole("form", { name: "Edit: Edric Thorne owes Lady Ashgrove" });
  await expect(edit.getByLabel("Staff note")).toHaveCount(0);
  await edit.getByLabel("Kind").selectOption("major");
  await edit.getByLabel("Why the edit").fill("Misheard at Elysium");
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  const theirs = boons.detail("Edric Thorne owes Lady Ashgrove, major");
  const theirLog = theirs.getByRole("list", { name: "Log of Edric Thorne owes Lady Ashgrove" });
  await expect(theirLog).toContainText("Misheard at Elysium");
  await expect(theirLog).toContainText("Philippa Quill");
  await expect(theirLog).not.toContainText("Kind: Minor → Major");
  await h.screenshot(shots("harpy-ledger"));

  // The lead sees the same edit, what it changed, and that Philippa made it.
  await l.goto(`/troupes/${troupe.id}/boons`);
  await ledgerOf(l).row("Edric Thorne owes Lady Ashgrove, major").click();
  const staffLog = ledgerOf(l).detail("Edric Thorne owes Lady Ashgrove, major").getByRole("list", { name: "Log of Edric Thorne owes Lady Ashgrove" });
  await expect(staffLog).toContainText("Kind: Minor → Major");
  await expect(staffLog).toContainText("as Philippa Quill");

  // Edric meets Final Death, and his player keeps him off the Who's Who (#975): staff see "Dead" beside his
  // name; the Harpy goes by what the court knows, and the court hasn't heard.
  await send(player.page, "POST", `/api/characters/${edric}/retire`, { reason: "final_death", note: "", listed: false });
  await l.reload();
  await showView(l, "departed");
  await expect(ledgerOf(l).row("Edric Thorne owes Lady Ashgrove, major").getByText("Dead", { exact: true }).filter({ visible: true })).toBeVisible();
  await expect(totalOf(l, "Departed")).not.toHaveAccessibleName("Departed 0");
  await h.reload();
  const atCourt = ledgerOf(h).row("Edric Thorne owes Lady Ashgrove, major");
  await expect(atCourt).toBeVisible();
  await expect(atCourt.getByText("Dead", { exact: true })).toHaveCount(0);
  // Its totals strip too (#977): the boon is still open as the court knows it.
  await expect(totalOf(h, "Departed")).toHaveAccessibleName("Departed 0");

  // Her ledger has staff's tabs, as far as she reaches (#982): To review holds the boon she named by name only,
  // flagged for a link; Boonbreakers and Audits are hers too.
  await boons.close();
  await expect(boonTab(h, "Boonbreakers")).toBeVisible();
  await expect(boonTab(h, "Audits")).toBeVisible();
  await boonTab(h, "To review").click();
  await expect(h).toHaveURL(new RegExp(`/play/characters/${philippa}/ledger/review$`));
  await expect(h.getByRole("list", { name: "Boons to review" }).getByRole("listitem", { name: /^To review: Edric Thorne owes Lady Ashgrove/ })).toBeVisible();
  // Given only the review queue, she sees just the queue: no tabs, no ledger.
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-harpy`, { access: "submissions" });
  await h.goto(`/play/characters/${philippa}/ledger`);
  await expect(h.getByRole("heading", { name: "Boons to review" })).toBeVisible();
  await expect(h.getByRole("list", { name: "Boons to review" })).toBeVisible();
  await expect(h.getByRole("navigation", { name: "Boons", exact: true })).toHaveCount(0);
  await expect(ledgerOf(h).table).toHaveCount(0);
});

test("the Harpy gives a Lesser Harpy add-only access: they register a boon as their character but can't edit it, then may settle but not correct it, and the Harpy, kept from it, doesn't see who did (#689, #984, #992)", async ({ browser }) => {
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
  await l.goto(`/troupes/${troupe.id}/boons#settings`);
  const lets = (await tabSettings(l, "Boons")).getByRole("checkbox", { name: /^The Harpy may give others access to the ledger/ });
  await lets.check();
  await expect(l.getByText("Saved: the Harpy may give others access to the ledger, as Lesser Harpies.")).toBeVisible();
  // And keeps what Lesser Harpies change from the Harpy (#992).
  const sees = (await tabSettings(l, "Boons")).getByRole("switch", { name: /^The Harpy sees what their talons change/ });
  await expect(sees).toBeChecked();
  await sees.click();
  await expect(l.getByText("Saved: what talons change is kept from the Harpy.")).toBeVisible();
  await expect(sees).not.toBeChecked();

  // Morwen's player makes Wren a Lesser Harpy who may add boons, nothing more.
  const h = harpy.page;
  await h.goto(`/play/characters/${morwen}/ledger`);
  await h.getByLabel("Make a Lesser Harpy").selectOption({ label: "Wren Ashby" });
  const may = h.getByRole("group", { name: "What they may do" });
  await expect(may.getByRole("checkbox", { name: "Add boons" })).toBeChecked();
  await expect(may.getByRole("checkbox", { name: "Correct boons" })).not.toBeChecked();
  await expect(may.getByRole("checkbox", { name: "Settle and move boons" })).not.toBeChecked();
  await h.getByRole("button", { name: "Give access" }).click();
  await expect(h.getByText("Wren Ashby has access to the ledger.")).toBeVisible();
  await expect(h.getByRole("list", { name: "Lesser Harpies" })).toContainText("Wren Ashby sees the ledger and adds boons");
  // With who gave it and the day, a date and not "NaN Nov 2026" (#998).
  await expect(h.getByRole("list", { name: "Lesser Harpies" })).toContainText(/Given by Morwen Vale, \d{1,2} [A-Z][a-z]{2} \d{4}/);

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
  // She doesn't review, so the totals strip has no To review (#977); and with the ledger all she reaches (no
  // review, audits or Boonbreakers, which are the Harpy's), there are no tabs (#982).
  await expect(totalOf(t, "Open")).toBeVisible();
  await expect(reviewTotal(t)).toHaveCount(0);
  await expect(t.getByRole("navigation", { name: "Boons", exact: true })).toHaveCount(0);

  // She can open it, but not edit, settle or void it: it has no Actions menu (#979).
  await ledgerOf(t).row("Wren Ashby owes Lady Morrow, minor").click();
  const debt = ledgerOf(t).detail("Wren Ashby owes Lady Morrow, minor");
  await expect(debt.getByRole("list", { name: "Log of Wren Ashby owes Lady Morrow" })).toContainText("Wren Ashby");
  await expect(ledgerOf(t).actions("Wren Ashby owes Lady Morrow, minor")).toHaveCount(0);
  await t.screenshot(shots("talon-ledger"));

  // The Harpy sees the boon, but not that Wren registered it (#992).
  const ledger = await (await h.request.get(`/api/troupes/${troupe.id}/boons`, { params: { view: "all" } })).json();
  const [registered] = ledger.boons;
  const opened = await (await h.request.get(`/api/troupes/${troupe.id}/boons/${registered.id}`)).json();
  expect(opened.events.map((e: { kind: string; as_character: string | null }) => [e.kind, e.as_character])).toEqual([["registered", null]]);

  // Morwen's player lets her settle and move boons too, but still not correct them (#984).
  await h
    .getByRole("group", { name: "What Wren Ashby may do" })
    .getByRole("checkbox", { name: "Settle and move boons" })
    .check();
  await expect(h.getByRole("list", { name: "Lesser Harpies" })).toContainText("Wren Ashby sees the ledger, adds boons and settles them");
  // The boon is in the address, so it opens again with the page.
  await t.reload();
  await expect(debt).toBeVisible();
  await ledgerOf(t).actions("Wren Ashby owes Lady Morrow, minor").click();
  const menu = t.getByRole("menu", { name: "Actions: Wren Ashby owes Lady Morrow, minor" });
  await expect(menu.getByRole("menuitem", { name: "Settle" })).toBeVisible();
  await expect(menu.getByRole("menuitem", { name: "Trade" })).toBeVisible();
  await expect(menu.getByRole("menuitem", { name: "Edit" })).toHaveCount(0);
});

test("in the Play View the Harpy keeps the ledger at a phone's width and a desk's: searches, opens a boon beside the table or over it, edits and settles it; each Lesser Harpy sees only their rights; offline nothing can be done (#985)", async ({ browser }) => {
  const custodian = await person(browser, "pvledger-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "pvledger-lead");
  const harpy = await person(browser, "pvledger-harpy");
  const talon = await person(browser, "pvledger-talon");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Ledger at Hand ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const isolde = await home(harpy.page, "Isolde Penhallow");
  const tobiah = await home(talon.page, "Tobiah Quarrel");
  const l = lead.page;
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-harpy`, { access: "full", export: true });
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-talons-setting`, { on: true, word: "Lesser Harpies" });
  await send(l, "PUT", `/api/troupes/${troupe.id}/characters/${isolde}/titles`, { titles: ["Harpy"] });
  await send(l, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [
      { debtor: { character_id: tobiah }, creditor: { name: "Lady Merrow" }, kind: "minor", made_on: "2026-10-03", reason: "Silence at the masque" },
      { debtor: { character_id: isolde }, creditor: { character_id: tobiah }, kind: "trivial", made_on: "2026-10-10", reason: "A seat at court" },
    ],
    note: "",
  });

  // At a game it is a phone: 375 px wide. At a desk, 1280.
  const narrow = async (page: Page) => {
    if (onPhone()) await page.setViewportSize({ width: 375, height: 800 });
  };
  /** Nothing on the page runs off its side. */
  const fits = (page: Page) => expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  /** A boon opened from the table: beside it from lg up, as on staff's page, and over the whole page on a phone. */
  const opened = async (page: Page, title: string) => {
    if (onPhone()) {
      await expect(page.getByRole("dialog", { name: title })).toBeVisible();
    } else {
      await expect(page.getByRole("complementary", { name: title })).toBeVisible();
      await expect(page.locator("dialog[open]")).toHaveCount(0);
      await expect(ledgerOf(page).table).toBeVisible();
    }
    await fits(page);
  };
  /** The ⓘ at the top of the ledger says what they may do, all of it on the screen. */
  const about = async (page: Page, note: string) => {
    await page.getByRole("button", { name: "About the boon ledger" }).click();
    const said = page.getByText(note);
    await expect(said).toBeVisible();
    await fits(page);
    await page.keyboard.press("Escape");
  };

  // Isolde's player opens the ledger from her Play View: the ⓘ says what she may do, and that it's logged as Isolde.
  const h = harpy.page;
  await narrow(h);
  await h.goto(`/play/characters/${isolde}/ledger`);
  const boons = ledgerOf(h);
  await expect(boons.rows).toHaveCount(2);
  await fits(h);
  await about(
    h,
    "As the troupe's Harpy you may register boons, correct them, settle and move them, approve what players report, perform audits and export the ledger. What you do is logged as your character.",
  );

  // She searches, opens the boon, corrects it and settles it.
  await h.getByRole("searchbox", { name: "Search the ledger" }).fill("masque");
  await expect(boons.rows).toHaveCount(1);
  await boons.open("Tobiah Quarrel owes Lady Merrow, minor");
  await opened(h, "Tobiah Quarrel owes Lady Merrow");
  await boons.act("Tobiah Quarrel owes Lady Merrow, minor", "Edit");
  const edit = boons.detail("Tobiah Quarrel owes Lady Merrow, minor").getByRole("form", { name: "Edit: Tobiah Quarrel owes Lady Merrow" });
  await edit.getByLabel("Kind").selectOption("major");
  await edit.getByLabel("Why the edit").fill("Misheard at the masque");
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  const debt = boons.detail("Tobiah Quarrel owes Lady Merrow, major");
  await expect(debt.getByRole("list", { name: "Log of Tobiah Quarrel owes Lady Merrow" })).toContainText("Isolde Penhallow");
  await boons.act("Tobiah Quarrel owes Lady Merrow, major", "Settle");
  await debt.getByRole("form", { name: "Settle: Tobiah Quarrel owes Lady Merrow" }).getByRole("button", { name: "Settle it" }).click();
  await expect(debt).toContainText("Settled: called in");
  await fits(h);
  await h.screenshot(shots("harpy-ledger-play"));

  // Offline, what shows stays, but nothing can be done with it, and the page says why.
  await h.context().setOffline(true);
  await expect(h.getByRole("status").filter({ hasText: "The ledger needs a signal." })).toBeVisible();
  await expect(boons.actions("Tobiah Quarrel owes Lady Merrow, major")).toBeDisabled();
  await boons.close();
  await expect(h.getByRole("button", { name: "Register boons" })).toBeDisabled();
  await expect(h.getByRole("button", { name: "More for the ledger" })).toBeDisabled();
  await h.context().setOffline(false);
  await expect(h.getByRole("button", { name: "Register boons" })).toBeEnabled();
  await expect(h.getByText("The ledger needs a signal.")).toHaveCount(0);

  // A name in a boon's detail opens their own page of the ledger (#980), the boon still beside it from lg up; offline, an audit waits.
  await h.getByRole("searchbox", { name: "Search the ledger" }).fill("");
  await boons.open("Isolde Penhallow owes Tobiah Quarrel, trivial");
  await boons.detail("Isolde Penhallow owes Tobiah Quarrel, trivial").getByRole("link", { name: "Tobiah Quarrel" }).click();
  const whose = h.getByRole("region", { name: "Whose boons" });
  await expect(whose.getByRole("heading", { name: "Tobiah Quarrel" })).toBeVisible();
  await expect(whose).toContainText("Owes 0 (weight 0) · Is owed 1 (weight 0.5)");
  await expect(h.getByRole("table", { name: "Is owed", exact: true }).getByRole("button", { name: /^Details: / })).toHaveCount(1);
  if (onPhone()) await expect(h.locator("dialog[open]")).toHaveCount(0);
  else await expect(h.getByRole("complementary", { name: "Isolde Penhallow owes Tobiah Quarrel" })).toBeVisible();
  await expect(whose.getByRole("link", { name: "Character sheet" })).toHaveCount(0);
  await expect(whose.getByRole("link", { name: "Make an audit" })).toBeVisible();
  await fits(h);
  await h.context().setOffline(true);
  await expect(whose.getByRole("button", { name: "Make an audit" })).toBeDisabled();
  await h.context().setOffline(false);
  await expect(whose.getByRole("link", { name: "Make an audit" })).toBeVisible();

  // A Lesser Harpy sees only what the Harpy lets them do: each right in turn.
  const t = talon.page;
  await narrow(t);
  const rights: { can: Record<string, boolean>; note: string; actions: string[]; register: boolean; exports: boolean; reviews: boolean }[] = [
    { can: { can_edit: true }, note: "As a Lesser Harpy you may correct boons.", actions: ["Edit"], register: false, exports: false, reviews: false },
    { can: { can_settle: true }, note: "As a Lesser Harpy you may settle and move boons.", actions: ["Trade", "Settle"], register: false, exports: false, reviews: false },
    // Approving reported boons is a right of its own (#993): the To review tab, and nothing to do in the ledger.
    { can: { can_review: true }, note: "As a Lesser Harpy you may approve what players report.", actions: [], register: false, exports: false, reviews: true },
    { can: { can_export: true }, note: "As a Lesser Harpy you may export the ledger.", actions: [], register: false, exports: true, reviews: false },
    { can: { can_add: true }, note: "As a Lesser Harpy you may register boons.", actions: [], register: true, exports: false, reviews: false },
  ];
  const seat = "Isolde Penhallow owes Tobiah Quarrel, trivial";
  for (const right of rights) {
    const none = { can_add: false, can_edit: false, can_settle: false, can_review: false, can_audit: false, can_export: false };
    await send(h, "PUT", `/api/troupes/${troupe.id}/boon-talons/${tobiah}`, { ...none, ...right.can });
    await t.goto(`/play/characters/${tobiah}/ledger`);
    const theirs = ledgerOf(t);
    await expect(theirs.row(seat)).toBeVisible();
    await fits(t);
    await about(t, right.note);
    await expect(t.getByRole("button", { name: "Register boons" })).toHaveCount(right.register ? 1 : 0);
    await expect(t.getByRole("button", { name: "More for the ledger" })).toHaveCount(right.exports ? 1 : 0);
    await expect(reviewTotal(t)).toHaveCount(right.reviews ? 1 : 0);
    await theirs.open(seat);
    await opened(t, "Isolde Penhallow owes Tobiah Quarrel");
    if (right.actions.length === 0) {
      await expect(theirs.actions(seat)).toHaveCount(0);
    } else {
      await theirs.actions(seat).click();
      const menu = t.getByRole("menu", { name: `Actions: ${seat}` });
      for (const action of ["Edit", "Trade", "Settle"])
        await expect(menu.getByRole("menuitem", { name: action, exact: true })).toHaveCount(right.actions.includes(action) ? 1 : 0);
      await t.keyboard.press("Escape");
    }
  }

  // Given only the review queue, the Harpy's page is the queue alone, at the Play View's width. With reports held
  // for approval (#993), one of Tobiah's waits there; offline, none of it can be accepted or not, nor its settings changed.
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-harpy`, { access: "submissions" });
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-review`, { hold: true });
  await send(t, "POST", `/api/characters/${tobiah}/play-boons`, { other: { character_id: isolde }, direction: "owes", kind: "minor", made_on: "2026-10-17", reason: "A word at the gate" });
  await h.goto(`/play/characters/${isolde}/ledger`);
  await expect(h.getByRole("heading", { name: "Boons to review" })).toBeVisible();
  await expect(ledgerOf(h).table).toHaveCount(0);
  const accept = h.getByRole("button", { name: "Accept: Tobiah Quarrel owes Isolde Penhallow", exact: true });
  await expect(accept).toBeEnabled();
  await fits(h);
  await h.context().setOffline(true);
  await expect(h.getByRole("status").filter({ hasText: "The ledger needs a signal." })).toBeVisible();
  await expect(accept).toBeDisabled();
  await expect(h.getByRole("button", { name: "Don't accept: Tobiah Quarrel owes Isolde Penhallow" })).toBeDisabled();
  await expect(h.getByRole("button", { name: /^Accept all shown/ })).toBeDisabled();
  await expect(h.getByRole("button", { name: "Approval settings" })).toBeDisabled();
  await h.context().setOffline(false);
  await expect(accept).toBeEnabled();
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
  await troupeTab(l, "Boons");
  // Boonbreakers are a tab of their own (#982), not on the ledger's front.
  await expect(totalOf(l, "Open")).toHaveAccessibleName("Open 2");
  await expect(l.getByRole("button", { name: "Declare a Boonbreaker" })).toHaveCount(0);
  await boonTab(l, "Boonbreakers").click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupe.id}/boons/boonbreakers$`));
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
  await expect(boonTab(l, "Boonbreakers")).toHaveAccessibleName("Boonbreakers 1 marked");
  await boonTab(l, "Ledger").click();
  await expect(totalOf(l, "Open")).toHaveAccessibleName("Open 0");
  await showView(l, "void");
  const voided = ledgerOf(l).row("Ottavia Sterne owes Lucan Mireaux, major");
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

  // Isolde's player, as the Harpy, audits Isolde's boons for Corin from the ledger's Audits tab (#982).
  const h = harpy.page;
  await h.goto(`/play/characters/${isolde}/ledger`);
  await boonTab(h, "Audits").click();
  await expect(h).toHaveURL(new RegExp(`/play/characters/${isolde}/ledger/audits$`));
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

test("where the troupe allows it, the Harpy reads the boon standings and statistics, with who has left as the court knows it (#749)", async ({ browser }) => {
  const custodian = await person(browser, "hstand-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "hstand-lead");
  const harpy = await person(browser, "hstand-harpy");
  const player = await person(browser, "hstand-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Court Remembers ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const oriel = await home(harpy.page, "Oriel Vane");
  const tamsin = await home(player.page, "Tamsin Rook");
  const silas = await home(player.page, "Silas Crane");
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/characters/${oriel}/titles`, { titles: ["Harpy"] });
  const owes = (debtor: string, creditor: string) => ({ debtor: { character_id: debtor }, creditor: { character_id: creditor }, kind: "minor", made_on: "2026-10-03", reason: "Information" });
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/boons`, { boons: [owes(tamsin, oriel), owes(silas, oriel)], note: "" });
  // Silas's player stops, and lists him under No longer with us: the court knows he's gone, never that his player stopped.
  await send(player.page, "POST", `/api/characters/${silas}/retire`, { reason: "inactive", note: "", listed: true });

  // The lead gives the Harpy the full ledger, then the standings and statistics too.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/boons#settings`);
  await tabSettings(l, "Boons");
  await l.getByRole("radio", { name: /^The full ledger/ }).check();
  await expect(l.getByText("Saved: The Harpy keeps the full ledger, and reviews the boons players report.")).toBeVisible();
  const reads = l.getByRole("switch", { name: /^The Harpy also reads the boon standings and statistics/ });
  await reads.check();
  await expect(l.getByText("Saved: the Harpy reads the boon standings and statistics.")).toBeVisible();
  await expect(reads).toBeChecked();

  // Oriel's player opens the standings from her ledger page.
  const h = harpy.page;
  await h.goto(`/play/characters/${oriel}/ledger`);
  await expect(h.getByText(`As Harpy of Court Remembers ${run}.`)).toBeVisible();
  await boonTab(h, "Standings").click();
  await expect(h.getByText("Who has left is shown as the court knows it.")).toBeVisible();
  await h.getByRole("radio", { name: "Everyone" }).check();
  const standing = h.getByRole("table", { name: "Standing by character" });
  await expect(standing).toContainText("Silas Crane (retired)");
  await expect(standing).toContainText("Tamsin Rook");
  await expect(h.locator("main")).not.toContainText("Inactive");
  // The weights read only: changing them is the staff's.
  await expect(h.getByRole("button", { name: "Edit the weights" })).toHaveCount(0);
  await h.screenshot(shots("harpy-standings"));

  await boonTab(h, "Statistics").click();
  await expect(h.getByRole("heading", { name: "Boon statistics" })).toBeVisible();
  await expect(h.locator("main")).not.toContainText("Inactive");
});
