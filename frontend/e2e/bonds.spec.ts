import { expect, test, type Page } from "@playwright/test";
import {
  closeContextsAfterEach,
  run,
  person,
  makeCustodian,
  builtVampire,
  ATTRIBUTES_AND_FOCUSES,
  backstoryOptional,
} from "./support";

/** Blood bonds: the troupe's setting, staff recording drinks on the Bonds screen, players reporting them (#661), and who sees them. */

closeContextsAfterEach();

test("staff record three drinks and the thrall's player sees a full bond; the regnant's player sees it only once told", async ({
  browser,
}) => {
  const custodian = await person(browser, "bonds-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bonds-lead");
  const thrall = await person(browser, "bonds-thrall");
  const regnant = await person(browser, "bonds-regnant");
  const headers = { "X-Horatio": "1" };
  const send = async (
    page: Page,
    method: "POST" | "PUT",
    url: string,
    data: object = {},
  ) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", {
    name: `Bound in Blood ${run}`,
    lead_handle: lead.handle,
  });
  await backstoryOptional(custodian.page, troupe.id);
  const build = {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [
      ["Fame", 3],
      ["Herd", 2],
      ["Generation", 1],
    ] as [string, number][],
    disciplines: [
      ["Celerity", 2],
      ["Potence", 1],
      ["Presence", 1],
    ] as [string, number][],
  };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    const asked = await send(
      page,
      "POST",
      `/api/characters/${id}/home-troupe`,
      { troupe_id: troupe.id },
    );
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const odile = await home(thrall.page, "Odile Marchand");
  const lucien = await home(regnant.page, "Lucien Vasse");

  // Bonds are off by default: no Bonds screen. The lead switches them on.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/settings`);
  const off = l.getByRole("radio", { name: /^Off/ });
  await expect(off).toBeChecked();
  await expect(l.getByRole("radio", { name: /^Players manage/ })).toBeEnabled();
  // Checked once the troupe saves it.
  await l.getByRole("radio", { name: /^Staff manages/ }).click();
  await expect(l.getByText(/^Blood bonds are tracked\./)).toBeVisible();
  await expect(l.getByRole("radio", { name: /^Staff manages/ })).toBeChecked();

  // The first drink, on the Bonds screen under Characters.
  await l
    .getByRole("navigation", { name: "Troupe sections" })
    .getByRole("link", { name: "Characters", exact: true })
    .click();
  await l.getByRole("link", { name: "Bonds", exact: true }).click();
  await expect(l.getByText("No blood bonds yet.")).toBeVisible();
  await l.getByRole("button", { name: "Record a drink" }).click();
  const record = l.getByRole("form", { name: "Record a drink" });
  await record.getByRole("combobox", { name: "Thrall" }).fill("Odile");
  await record
    .getByRole("listbox", { name: "Characters" })
    .getByRole("option", { name: /Odile Marchand/ })
    .click();
  await record.getByRole("combobox", { name: "Regnant" }).fill("Lucien");
  await record
    .getByRole("listbox", { name: "Characters" })
    .getByRole("option", { name: /Lucien Vasse/ })
    .click();
  await record.getByLabel("Night").fill("2026-10-03");
  await record.getByLabel("Note (optional)").fill("A toast at Elysium");
  await record.getByRole("button", { name: "Record the drink" }).click();
  const bond = l.getByRole("listitem", {
    name: "Odile Marchand bound to Lucien Vasse",
  });
  await expect(bond).toContainText("First drink");

  // Two more, on two more nights: a full bond.
  for (const [night, level] of [
    ["2026-10-10", "Second drink"],
    ["2026-10-17", "Full bond"],
  ]) {
    await bond.getByRole("button", { name: "Add a drink" }).click();
    const drink = bond.getByRole("form", {
      name: "Add a drink: Odile Marchand from Lucien Vasse",
    });
    await drink.getByLabel("Night").fill(night!);
    await drink.getByRole("button", { name: "Add the drink" }).click();
    await expect(bond).toContainText(level!);
  }
  await bond.getByRole("button", { name: /^Drinks log/ }).click();
  await expect(
    bond
      .getByRole("list", {
        name: "Drinks log of Odile Marchand bound to Lucien Vasse",
      })
      .getByRole("listitem"),
  ).toHaveCount(3);
  await expect(bond).toContainText("A toast at Elysium");

  // Odile's player sees the full bond on her sheet.
  const t = thrall.page;
  await t.goto(`/characters/${odile}`);
  const bound = t.getByRole("list", { name: "Bound to" });
  await expect(bound).toContainText("Bound to Lucien Vasse");
  await expect(bound).toContainText(
    "Full bond: they come before everyone else",
  );

  // Lucien's player isn't told until the lead marks it known to him.
  const r = regnant.page;
  const before = await (
    await r.request.get(`/api/characters/${lucien}/bonds`)
  ).json();
  expect(before.bound_by).toEqual([]);
  await bond.getByLabel("Known to Lucien Vasse: their player sees it").click();
  await expect(
    bond.getByLabel("Known to Lucien Vasse: their player sees it"),
  ).toBeChecked();
  await r.goto(`/characters/${lucien}`);
  await expect(r.getByRole("list", { name: "Bound to you" })).toContainText(
    "Odile Marchand: full bond",
  );
  // Neither player can open the Bonds screen.
  const refused = await r.request.get(`/api/troupes/${troupe.id}/bonds`);
  expect(refused.status()).toBe(403);
});

test("staff see the troupe's bonds as a web: a full bond is a heavy link, and a chain is named (#708)", async ({ browser }) => {
  const custodian = await person(browser, "bondweb-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bondweb-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", `/api/troupes`, { name: `Web of Blood ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  await send(l, "PUT", `/api/troupes/${troupe.id}/blood-bonds`, { setting: "staff" });
  const tavish = await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Tavish Morrow" });
  const drink = (thrall: object, regnant: object, night: string) => send(l, "POST", `/api/troupes/${troupe.id}/bonds/drinks`, { thrall, regnant, night, source: "game" });
  // Wren is fully bound to Tavish; Ida has had one drink of him; Tavish himself has drunk twice from the Margrave.
  for (const night of ["2026-10-03", "2026-10-10", "2026-10-17"]) await drink({ name: "Wren Ashdown" }, { character_id: tavish.id }, night);
  await drink({ name: "Ida Coyle" }, { character_id: tavish.id }, "2026-10-03");
  for (const night of ["2026-10-03", "2026-10-10"]) await drink({ character_id: tavish.id }, { name: "The Margrave" }, night);

  await l.goto(`/troupes/${troupe.id}/bonds`);
  await l.getByRole("navigation", { name: "Blood bonds" }).getByRole("link", { name: "Web" }).click();
  const chart = l.getByRole("figure", { name: "The web of blood bonds" });
  await expect(chart).toBeVisible();
  // The full bond is drawn heaviest; the single drink lightest.
  const full = chart.locator('[data-bond="Wren Ashdown → Tavish Morrow"] line[data-level="3"]');
  await expect(full).toHaveAttribute("stroke-width", "5");
  await expect(chart.locator('[data-bond="Ida Coyle → Tavish Morrow"] line[data-level="1"]')).toHaveAttribute("stroke-width", "1.5");
  await expect(l.getByRole("region", { name: "Most thralls" })).toContainText("Tavish Morrow2 (1 full)");
  await expect(l.getByRole("region", { name: "Chains of bonds" })).toContainText("Ida Coyle, Wren Ashdown → Tavish Morrow → The Margrave");
  // Full bonds only leaves the one.
  await l.getByRole("group", { name: "Bonds" }).getByRole("button", { name: "Full bonds" }).click();
  await expect(chart.locator("[data-bond]")).toHaveCount(1);
  await l.getByRole("group", { name: "Bonds" }).getByRole("button", { name: "Every level" }).click();
  await expect(chart.locator("[data-bond]")).toHaveCount(3);

  // Selecting Tavish opens his bonds on the list.
  await chart.locator('[data-person="Tavish Morrow"] circle').nth(1).click();
  await l.getByRole("link", { name: "Open their bonds" }).click();
  await expect(l.getByText("Showing only Tavish Morrow's bonds.")).toBeVisible();
  await expect(l.getByRole("region", { name: "Wren Ashdown" })).toBeVisible();

  // Players never get it.
  const player = await person(browser, "bondweb-player");
  expect((await player.page.request.get(`/api/troupes/${troupe.id}/bond-web`)).status()).toBe(403);
});

test("players report a drink for staff to approve; under Players manage the thrall confirms one the regnant recorded", async ({
  browser,
}) => {
  const custodian = await person(browser, "bondrep-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bondrep-lead");
  const thrall = await person(browser, "bondrep-thrall");
  const regnant = await person(browser, "bondrep-regnant");
  const headers = { "X-Horatio": "1" };
  const send = async (
    page: Page,
    method: "POST" | "PUT",
    url: string,
    data: object = {},
  ) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", {
    name: `Chalice Court ${run}`,
    lead_handle: lead.handle,
  });
  await backstoryOptional(custodian.page, troupe.id);
  const build = {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [
      ["Fame", 3],
      ["Herd", 2],
      ["Generation", 1],
    ] as [string, number][],
    disciplines: [
      ["Celerity", 2],
      ["Potence", 1],
      ["Presence", 1],
    ] as [string, number][],
  };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    const asked = await send(
      page,
      "POST",
      `/api/characters/${id}/home-troupe`,
      { troupe_id: troupe.id },
    );
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const severine = await home(thrall.page, "Séverine Arlaud");
  const corentin = await home(regnant.page, "Corentin Mallet");
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/blood-bonds`, {
    setting: "players_report",
  });

  // Séverine's player reports a drink from her sheet: it waits on the storytellers.
  const t = thrall.page;
  await t.goto(`/characters/${severine}`);
  await t.getByRole("button", { name: "Report a drink", exact: true }).click();
  const form = t.getByRole("form", { name: "Report a drink" });
  await form.getByRole("combobox", { name: "Whose blood" }).fill("Corentin");
  await form
    .getByRole("listbox", { name: "Characters" })
    .getByRole("option", { name: /Corentin Mallet/ })
    .click();
  await form.getByLabel("Note (optional)").fill("A sip at the masque");
  await form.getByRole("button", { name: "Report the drink" }).click();
  await expect(
    t.getByText("Sent to the storytellers to approve."),
  ).toBeVisible();
  const reported = t.getByRole("list", { name: "Drinks reported" });
  await expect(reported).toContainText(
    "Séverine Arlaud drank Corentin Mallet's blood",
  );
  await expect(reported).toContainText("Waiting for the storytellers");
  // Corentin's player hears nothing of it.
  const unseen = await (
    await regnant.page.request.get(`/api/characters/${corentin}/bonds`)
  ).json();
  expect([unseen.bound_by, unseen.reports]).toEqual([[], []]);

  // The lead approves it in Approvals.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/approvals`);
  await expect(
    l.getByText("Reports Séverine Arlaud drinking Corentin Mallet's blood"),
  ).toBeVisible();
  await l.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();
  await t.reload();
  await expect(t.getByRole("list", { name: "Bound to" })).toContainText(
    "Bound to Corentin Mallet",
  );
  await expect(t.getByRole("list", { name: "Drinks reported" })).toContainText(
    "Counted",
  );

  // Under Players manage, Corentin's player records that Séverine drank his blood, in the Play View.
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/blood-bonds`, {
    setting: "players_manage",
  });
  const r = regnant.page;
  await r.goto(`/play/characters/${corentin}?tab=tracker`);
  await r
    .getByRole("button", { name: "Report a drink of vampire blood" })
    .click();
  const play = r.getByRole("form", { name: "Report a drink" });
  await play.getByLabel("Someone drank Corentin Mallet's blood").check();
  await play.getByRole("combobox", { name: "Who drank it" }).fill("Séverine");
  await play
    .getByRole("listbox", { name: "Characters" })
    .getByRole("option", { name: /Séverine Arlaud/ })
    .click();
  await play.getByRole("button", { name: "Report the drink" }).click();
  await expect(
    r.getByText("Sent to Séverine Arlaud's player to confirm."),
  ).toBeVisible();

  // It waits on Séverine's player, who confirms it; then the bond is known to Corentin.
  await t.reload();
  const asking = t
    .getByRole("listitem", {
      name: /^Séverine Arlaud drank Corentin Mallet's blood/,
    })
    .filter({ hasText: "Did it happen?" });
  await asking.getByRole("button", { name: "Confirm" }).click();
  await expect(t.getByText("Did it happen?")).toHaveCount(0);
  await r.goto(`/characters/${corentin}`);
  await expect(r.getByRole("list", { name: "Bound to you" })).toContainText(
    "Séverine Arlaud: first drink",
  );
});

test("a dead regnant's bond fades: staff see the day it ends, and the thrall's sheet doesn't change (#662)", async ({
  browser,
}) => {
  const custodian = await person(browser, "gonefade-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "gonefade-lead");
  const thrall = await person(browser, "gonefade-thrall");
  const regnant = await person(browser, "gonefade-regnant");
  const headers = { "X-Horatio": "1" };
  const send = async (
    page: Page,
    method: "POST" | "PUT",
    url: string,
    data: object = {},
  ) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", {
    name: `Ashen Vigil ${run}`,
    lead_handle: lead.handle,
  });
  await backstoryOptional(custodian.page, troupe.id);
  const build = {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [
      ["Fame", 3],
      ["Herd", 2],
      ["Generation", 1],
    ] as [string, number][],
    disciplines: [
      ["Celerity", 2],
      ["Potence", 1],
      ["Presence", 1],
    ] as [string, number][],
  };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    const asked = await send(
      page,
      "POST",
      `/api/characters/${id}/home-troupe`,
      { troupe_id: troupe.id },
    );
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id;
  };
  const solene = await home(thrall.page, "Solene Ardoise");
  const hale = await home(regnant.page, "Malachai Hale");
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/blood-bonds`, {
    setting: "staff",
  });
  for (const night of ["2026-10-03", "2026-10-10"]) {
    await send(lead.page, "POST", `/api/troupes/${troupe.id}/bonds/drinks`, {
      thrall: { character_id: solene },
      regnant: { character_id: hale },
      night,
      source: "game",
    });
  }

  // Solene's player sees two drinks.
  const t = thrall.page;
  await t.goto(`/characters/${solene}`);
  const bound = t.getByRole("list", { name: "Bound to" });
  await expect(bound).toContainText("Bound to Malachai Hale");
  const before = (await bound.textContent()) ?? "";

  // Malachai meets Final Death: his player retires him.
  await send(regnant.page, "POST", `/api/characters/${hale}/retire`, {
    reason: "final_death",
    note: "Sunrise",
    listed: false,
  });

  // Staff see the bond fading, with the day it ends.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/bonds`);
  const bond = l.getByRole("listitem", {
    name: "Solene Ardoise bound to Malachai Hale",
  });
  await expect(bond).toContainText(
    "Fading: Malachai Hale met Final Death, and it ends on",
  );
  // Solene's player sees nothing change.
  await t.reload();
  await expect(bound).toHaveText(before);

  // Staff end it today, as the 30 days running out would: it has faded, but Solene's
  // player isn't told until the next downtime results, so her sheet still shows it.
  await bond.getByRole("button", { name: "Change the fade" }).click();
  const fade = bond.getByRole("form", {
    name: "Change the fade of Solene Ardoise's bond to Malachai Hale",
  });
  await fade.getByRole("button", { name: "Today" }).click();
  await fade.getByLabel("Reason").fill("The story moves on");
  await fade.getByRole("button", { name: "Save the fade" }).click();
  await expect(bond).toContainText(
    "Ended: Faded: its regnant met Final Death.",
  );
  await expect(bond).toContainText("Solene Ardoise's player isn't told yet");
  await t.reload();
  await expect(bound).toHaveText(before);
});

test("bonds Horatio knows by rule: staff fill in a ghoul's from before, and a new domitor moves it (#663)", async ({
  browser,
}) => {
  const custodian = await person(browser, "kinbond-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "kinbond-lead");
  const headers = { "X-Horatio": "1" };
  const send = async (
    page: Page,
    method: "POST" | "PUT",
    url: string,
    data: object = {},
  ) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", {
    name: `Hollow Lantern ${run}`,
    lead_handle: lead.handle,
  });
  // A ghoul NPC bound to her domitor while the troupe didn't track bonds.
  const l = lead.page;
  const perrine = await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, {
    name: "Perrine Valcourt",
    npc_kind: "ghoul",
  });
  await send(l, "PUT", `/api/characters/${perrine.id}/domitor`, {
    name: "Aurelien Thorne",
    clan: "Toreador",
  });
  await send(l, "PUT", `/api/troupes/${troupe.id}/blood-bonds`, {
    setting: "staff",
  });

  // Switched on, Horatio offers what it knows, and adds it when staff say so.
  await l.goto(`/troupes/${troupe.id}/bonds`);
  await expect(l.getByText("No blood bonds yet.")).toBeVisible();
  const known = l.getByRole("list", { name: "Known bonds" });
  await expect(known).toContainText(
    "Perrine Valcourt to Aurelien Thorne, Full bond from",
  );
  await expect(known).toContainText("(their domitor)");
  await l.getByRole("button", { name: "Add this bond" }).click();
  const bond = l.getByRole("listitem", {
    name: "Perrine Valcourt bound to Aurelien Thorne",
  });
  await expect(bond).toContainText("Full bond");
  await expect(known).toHaveCount(0);

  // A new domitor: the old bond ends, as faded before the change, and she is bound to the new one.
  await send(l, "PUT", `/api/characters/${perrine.id}/domitor`, {
    name: "Remy Castellane",
    clan: "Brujah",
  });
  await l.reload();
  await expect(
    l.getByRole("listitem", { name: "Perrine Valcourt bound to Remy Castellane" }),
  ).toContainText("Full bond");
  await expect(
    l.getByRole("listitem", {
      name: "Perrine Valcourt bound to Aurelien Thorne",
    }),
  ).toHaveCount(0);
  await l.getByLabel(/^Show ended and broken bonds/).check();
  await expect(bond).toContainText("the bond to the old one had faded");
});
