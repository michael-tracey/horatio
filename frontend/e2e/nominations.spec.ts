import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, backstoryOptional, switchFeature } from "./support";

/** Player Nominations (#470): written in a downtime, reviewed and published by staff, read by the troupe. */

closeContextsAfterEach();

const headers = { "X-Horatio": "1" };

async function send(page: Page, method: "GET" | "POST" | "PUT", url: string, data?: object) {
  const response = await page.request.fetch(url, { method, headers, data: method === "GET" ? undefined : (data ?? {}) });
  expect(response.status(), await response.text()).toBeLessThan(300);
  return response.json();
}

/** A finished character whose home troupe this is, accepted by its lead. */
async function member(page: Page, lead: Page, troupeId: string, name: string): Promise<string> {
  const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
  await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const picks: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, list] of Object.entries(picks))
    await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
  await send(page, "POST", `/api/characters/${id}/creation/complete`);
  const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  await send(lead, "POST", `/api/approvals/${asked.id}/approve`);
  return id;
}

test("players write Player Nominations in their downtime, staff review, star and publish them, and the troupe reads them without names", async ({ browser }) => {
  const custodian = await person(browser, "nominee-custod");
  makeCustodian(custodian.email);
  const lead = await person(browser, "nominee-lead");
  const writer = await person(browser, "nominee-writer");
  const reader = await person(browser, "nominee-reader");
  await custodian.page.reload();
  const troupeName = `Gilded Salon ${run}`;
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const ada = await member(writer.page, lead.page, troupe.id, "Ada Vesper");
  const bel = await member(reader.page, lead.page, troupe.id, "Bel Marrow");
  // A cycle already past Due, still taking downtimes in its grace period.
  const now = Date.now();
  const cycle = await send(lead.page, "POST", `/api/troupes/${troupe.id}/cycles`, {
    name: "Salon month",
    closes_at: new Date(now - 60e3).toISOString(),
    grace_ends_at: new Date(now + 2 * 86400e3).toISOString(),
  });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/open`);

  // While the troupe doesn't use them, nothing of them shows.
  const w = writer.page;
  await w.goto(`/characters/${ada}/downtime`);
  await expect(w.getByRole("button", { name: "Submit downtime" })).toBeVisible();
  await expect(w.getByRole("heading", { name: "Player Nominations" })).toHaveCount(0);
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/downtimes/${cycle.id}`);
  await expect(l.getByRole("link", { name: "Responses" })).toBeVisible();
  await expect(l.getByRole("link", { name: "Nominations" })).toHaveCount(0);

  // The lead switches them on in the Features list, under Customise › Troupe settings.
  await switchFeature(l, troupe.id, "Player Nominations", true);

  // The writer adds two to their downtime: one about Bel, one about no one.
  await w.reload();
  const section = w.locator("section").filter({ has: w.getByRole("heading", { name: "Player Nominations" }) });
  await expect(section.getByText(/shared with the troupe without your name, and the storytellers read them first/)).toBeVisible();
  await section.getByLabel("New nomination").fill("Bel's eulogy at the salon had the whole room in tears.");
  await section.getByLabel("About (optional)").selectOption({ label: "Bel Marrow" });
  await section.getByRole("button", { name: "Add nomination" }).click();
  const mine = section.getByRole("list", { name: "Your nominations" });
  await expect(mine.getByText("About Bel Marrow")).toBeVisible();
  await section.getByLabel("New nomination").fill("Thanks to everyone for a gentle, generous night.");
  await section.getByRole("button", { name: "Add nomination" }).click();
  await expect(mine.getByRole("listitem")).toHaveCount(2);
  await w.screenshot(shots("nominations-write"));
  await w.getByRole("button", { name: "Submit downtime" }).click();
  await expect(w.getByText(/^Submitted\./)).toBeVisible();

  // The lead reviews them on the cycle's Nominations tab, with who wrote each.
  await l.goto(`/troupes/${troupe.id}/downtimes/${cycle.id}/nominations`);
  const table = l.getByRole("table", { name: "Player Nominations" });
  await expect(table.getByRole("row")).toHaveCount(3);
  await expect(l.getByText("2 written · 0 removed · 0 starred")).toBeVisible();
  await expect(table).toContainText("Ada Vesper");
  await l.getByRole("button", { name: "Actions for “Bel's eulogy at the salon had the whole…”" }).click();
  await l.getByRole("menuitem", { name: "Star", exact: true }).click();
  await expect(l.getByText("2 written · 0 removed · 1 starred")).toBeVisible();
  await l.screenshot(shots("nominations-review"));
  await l.getByRole("button", { name: "Publish nominations" }).click();
  await expect(l.getByText("Published 2 nominations.")).toBeVisible();
  await expect(l.getByText(/^Published \d{1,2} [A-Z][a-z]{2} \d{4}/)).toBeVisible();

  // Bel's player reads the month, without names, with the starred one in the footer.
  const r = reader.page;
  await r.goto(`/troupes/${troupe.id}/nominations`);
  const month = r.getByRole("list", { name: "Salon month's Player Nominations" });
  await expect(month.getByRole("listitem")).toHaveCount(2);
  await expect(month.getByText("Bel's eulogy at the salon had the whole room in tears.")).toBeVisible();
  await expect(month.getByText("About Bel Marrow · Starred")).toBeVisible();
  await expect(r.locator("main")).not.toContainText("Ada Vesper");
  await expect(r.locator("main")).not.toContainText("nominee-writer");
  const footer = r.getByRole("complementary", { name: "Player Nominations" });
  await expect(footer.getByText("“Bel's eulogy at the salon had the whole room in tears.”")).toBeVisible();
  await expect(footer.getByText("Player Nominations, Salon month")).toBeVisible();
  await r.screenshot(shots("nominations-page"));

  // On Bel's own page, the one about Bel.
  await r.goto(`/characters/${bel}`);
  const about = r.locator("section").filter({ has: r.getByRole("heading", { name: "Nominations about Bel Marrow" }) });
  await expect(about.getByText("Bel's eulogy at the salon had the whole room in tears.")).toBeVisible();
  await expect(about.getByText(`${troupeName}, Salon month`)).toBeVisible();
  await expect(about).not.toContainText("gentle, generous");
});

test("a character retires with remembrances, the next downtime asks for a memory, staff publish it, and its player reads it on its page", async ({ browser }) => {
  const custodian = await person(browser, "rememb-custod");
  makeCustodian(custodian.email);
  const lead = await person(browser, "rememb-lead");
  const gone = await person(browser, "rememb-gone");
  const friend = await person(browser, "rememb-friend");
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Lantern Court ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const vera = await member(gone.page, lead.page, troupe.id, "Vera Lune");
  const otto = await member(friend.page, lead.page, troupe.id, "Otto Reyes");

  // The lead switches Remembrances on; Player Nominations stay off.
  const l = lead.page;
  await switchFeature(l, troupe.id, "Remembrances", true);
  await expect(l.getByRole("list", { name: "Features" }).getByRole("switch", { name: "Player Nominations", exact: true })).toHaveAttribute("aria-checked", "false");

  // Vera's player retires her, Final Death, and asks for remembrances.
  const g = gone.page;
  await g.goto(`/characters/${vera}`);
  await g.getByRole("button", { name: "More for Vera Lune" }).click();
  await g.getByRole("menuitem", { name: "Retire…" }).click();
  const dialog = g.getByRole("dialog", { name: "Retire Vera Lune" });
  await dialog.getByRole("radio", { name: /^Final Death/ }).check();
  await dialog.getByRole("checkbox", { name: /^Ask the storytellers to open remembrances in the next downtime/ }).check();
  await g.screenshot(shots("remembrances-retire"));
  await dialog.getByRole("button", { name: "Retire Vera Lune" }).click();
  await expect(g.getByText("Why Vera Lune left: Final Death.")).toBeVisible();
  const card = (p: Page) => p.locator("section").filter({ has: p.getByRole("heading", { name: "Remembrances", exact: true }) });
  await expect(card(g).getByText("Vera Lune’s player asked for remembrances.")).toBeVisible();

  // The lead opens them from her page: no cycle is open, so the next one asks.
  await l.goto(`/characters/${vera}`);
  await expect(card(l).getByText(/Opened now, they’re asked for in the next downtime cycle that opens\./)).toBeVisible();
  await card(l).getByRole("button", { name: "Open remembrances" }).click();
  await expect(card(l).getByText("The troupe is asked for memories of Vera Lune in the next downtime cycle that opens.")).toBeVisible();
  // A cycle already past Due, still taking downtimes in its grace period.
  const now = Date.now();
  const cycle = await send(l, "POST", `/api/troupes/${troupe.id}/cycles`, {
    name: "Lantern month",
    closes_at: new Date(now - 60e3).toISOString(),
    grace_ends_at: new Date(now + 2 * 86400e3).toISOString(),
  });
  await send(l, "POST", `/api/cycles/${cycle.id}/open`);

  // Otto's player writes a memory of her in the next downtime.
  const f = friend.page;
  await f.goto(`/characters/${otto}/downtime`);
  const memory = f.getByRole("listitem", { name: "A memory of Vera Lune" });
  await expect(memory.getByText("Final Death")).toBeVisible();
  await expect(f.getByRole("heading", { name: "Player Nominations" })).toHaveCount(0);
  await memory.getByLabel("Your memory of Vera Lune").fill("She lit every lantern in the court the night we lost the Prince.");
  await memory.getByRole("button", { name: "Save memory" }).click();
  await expect(memory.getByText("Saved", { exact: true })).toBeVisible();
  await f.screenshot(shots("remembrances-write"));
  await f.getByRole("button", { name: "Submit downtime" }).click();
  await expect(f.getByText(/^Submitted\./)).toBeVisible();

  // The lead reviews it, with its writer, and publishes.
  await l.goto(`/troupes/${troupe.id}/downtimes/${cycle.id}/nominations`);
  const memories = l.getByRole("table", { name: "Memories of Vera Lune" });
  await expect(memories).toContainText("She lit every lantern");
  await expect(memories).toContainText("Otto Reyes");
  await l.getByRole("button", { name: "Publish remembrances" }).click();
  await expect(l.getByText("Published 1 memory.")).toBeVisible();

  // Vera's player reads it on her page, without who wrote it.
  await g.goto(`/characters/${vera}`);
  await expect(card(g).getByRole("region", { name: "Remembrances of Vera Lune, Lantern month" })).toContainText(
    "She lit every lantern in the court the night we lost the Prince.",
  );
  await expect(card(g)).not.toContainText("Otto");
  await g.screenshot(shots("remembrances-read"));

  // Otto's player finds it from Vera's entry on the Who's Who.
  await f.goto(`/troupes/${troupe.id}/whos-who`);
  await f.getByRole("article", { name: "Vera Lune" }).getByRole("button", { name: "Remembrances" }).click();
  await expect(f.getByRole("dialog", { name: "Remembrances of Vera Lune" })).toContainText("She lit every lantern");
});
