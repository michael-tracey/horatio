import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, person, makeCustodian, builtVampire, ATTRIBUTES_AND_FOCUSES, backstoryOptional } from "./support";

/** Blood bonds: the troupe's setting, staff recording drinks on the Bonds screen, and who sees them. */

closeContextsAfterEach();

test("staff record three drinks and the thrall's player sees a full bond; the regnant's player sees it only once told", async ({ browser }) => {
  const custodian = await person(browser, "bonds-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bonds-lead");
  const thrall = await person(browser, "bonds-thrall");
  const regnant = await person(browser, "bonds-regnant");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Bound in Blood ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const build = { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const home = async (page: Page, name: string) => {
    const id = await builtVampire(page, name, "Brujah", build);
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
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
  await expect(l.getByRole("radio", { name: /^Players manage/ })).toBeDisabled();
  // Checked once the troupe saves it.
  await l.getByRole("radio", { name: /^Staff manages/ }).click();
  await expect(l.getByText(/^Blood bonds are tracked\./)).toBeVisible();
  await expect(l.getByRole("radio", { name: /^Staff manages/ })).toBeChecked();

  // The first drink, on the Bonds screen under Characters.
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: "Bonds", exact: true }).click();
  await expect(l.getByText("No blood bonds yet.")).toBeVisible();
  await l.getByRole("button", { name: "Record a drink" }).click();
  const record = l.getByRole("form", { name: "Record a drink" });
  await record.getByRole("combobox", { name: "Thrall" }).fill("Odile");
  await record.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Odile Marchand/ }).click();
  await record.getByRole("combobox", { name: "Regnant" }).fill("Lucien");
  await record.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Lucien Vasse/ }).click();
  await record.getByLabel("Night").fill("2026-10-03");
  await record.getByLabel("Note (optional)").fill("A toast at Elysium");
  await record.getByRole("button", { name: "Record the drink" }).click();
  const bond = l.getByRole("listitem", { name: "Odile Marchand bound to Lucien Vasse" });
  await expect(bond).toContainText("First drink");

  // Two more, on two more nights: a full bond.
  for (const [night, level] of [
    ["2026-10-10", "Second drink"],
    ["2026-10-17", "Full bond"],
  ]) {
    await bond.getByRole("button", { name: "Add a drink" }).click();
    const drink = bond.getByRole("form", { name: "Add a drink: Odile Marchand from Lucien Vasse" });
    await drink.getByLabel("Night").fill(night!);
    await drink.getByRole("button", { name: "Add the drink" }).click();
    await expect(bond).toContainText(level!);
  }
  await bond.getByRole("button", { name: /^Drinks log/ }).click();
  await expect(bond.getByRole("list", { name: "Drinks log of Odile Marchand bound to Lucien Vasse" }).getByRole("listitem")).toHaveCount(3);
  await expect(bond).toContainText("A toast at Elysium");

  // Odile's player sees the full bond on her sheet.
  const t = thrall.page;
  await t.goto(`/characters/${odile}`);
  const bound = t.getByRole("list", { name: "Bound to" });
  await expect(bound).toContainText("Bound to Lucien Vasse");
  await expect(bound).toContainText("Full bond: they come before everyone else");

  // Lucien's player isn't told until the lead marks it known to him.
  const r = regnant.page;
  const before = await (await r.request.get(`/api/characters/${lucien}/bonds`)).json();
  expect(before.bound_by).toEqual([]);
  await bond.getByLabel("Known to Lucien Vasse: their player sees it").click();
  await expect(bond.getByLabel("Known to Lucien Vasse: their player sees it")).toBeChecked();
  await r.goto(`/characters/${lucien}`);
  await expect(r.getByRole("list", { name: "Bound to you" })).toContainText("Odile Marchand: full bond");
  // Neither player can open the Bonds screen.
  const refused = await r.request.get(`/api/troupes/${troupe.id}/bonds`);
  expect(refused.status()).toBe(403);
});
