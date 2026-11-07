import { expect, test, type Locator, type Page } from "@playwright/test";
import { closeContextsAfterEach, person, makeCustodian, ATTRIBUTES_AND_FOCUSES } from "./support";

/**
 * The screenshots in the Players part of the manual (docs/manual/players.md, #483).
 * Not a test of the app: it makes a fictional troupe and player, walks them through
 * the screens a player uses, and saves cropped pictures of them. CI never runs it:
 *
 *   MANUAL_SHOTS=1 ./e2e-local.sh -- e2e/manual-players.spec.ts --project=desktop
 */

test.skip(!process.env.MANUAL_SHOTS, "manual screenshots: run with MANUAL_SHOTS=1");

closeContextsAfterEach();

const headers = { "X-Horatio": "1" };
const shot = (name: string) => ({ path: `../docs/manual/images/players/${name}.png` });

async function send(page: Page, method: "GET" | "POST" | "PUT", url: string, data?: object) {
  const response = await page.request.fetch(url, { method, headers, data });
  expect(response.status(), `${method} ${url}: ${await response.text()}`).toBeLessThan(300);
  return response.json();
}

/** A card on the page by its title (ui.tsx's Card: a section whose header holds an h2). */
function card(page: Page, title: string): Locator {
  return page.locator(`xpath=//section[header//h2[normalize-space()="${title}"]]`).first();
}

/** Places every pick of the vampire's creation through the API: the usual attributes,
 * focuses and skills, three backgrounds with Generation, and its in-clan disciplines. */
async function placePicks(p: Page, id: string) {
  for (const [category, picks] of Object.entries({
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Contacts", 3], ["Herd", 2], ["Generation", 1]] as [string, number][],
  }))
    await send(p, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  const creation: { pools: { category: string; kind: string; rating: number; allowed: number; restriction: string | null; options: string[] | null }[] } = await send(
    p,
    "GET",
    `/api/characters/${id}/creation`,
  );
  const pools = creation.pools.filter((pool) => pool.category === "disciplines" && pool.kind === "picks").sort((a, b) => b.rating - a.rating);
  const inClan = [...(creation.pools.find((pool) => pool.restriction === "in_clan")?.options ?? [])];
  const picks = pools.flatMap((pool) => Array.from({ length: pool.allowed }, () => ({ name: inClan.shift()!, rating: pool.rating })));
  await send(p, "PUT", `/api/characters/${id}/creation/categories/disciplines`, { picks });
}

test("screenshots for the Players part of the manual", async ({ browser }) => {
  test.skip(test.info().project.name !== "desktop", "manual screenshots are taken on the desktop only");
  test.setTimeout(600_000);
  const custodian = await person(browser, "manual-pl-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "manual-pl-lead");
  const player = await person(browser, "manual-pl-player");
  const l = lead.page;
  const p = player.page;
  await send(l, "PUT", "/api/profile", { display_name: "Morgan Hale" });
  await send(p, "PUT", "/api/profile", { display_name: "Rhea Calloway" });

  // The troupe: no backstory needed before accepting, and Brawl priced its own way.
  await custodian.page.reload();
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: "Court of Ashes", lead_handle: lead.handle });
  await send(l, "PUT", `/api/troupes/${troupeId}/backstory-settings`, { mode: "free", required: false });
  await send(l, "POST", `/api/troupes/${troupeId}/costs`, { category: "skills", trait: "Brawl", scheme: "per_dot", rate: 1 });

  // The wizard's Concept step: a bloodline chosen, with what it means.
  await p.reload();
  await p.getByLabel("Name").fill("Theo Vance");
  await p.getByLabel("Which troupe will you play in?").selectOption({ label: "Court of Ashes" });
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept", exact: true })).toBeVisible();
  const theo = new URL(p.url()).pathname.split("/")[2]!;
  await p.getByLabel("Clan").selectOption("Gangrel: Coyote");
  await expect(p.getByRole("region", { name: /^About Gangrel/ })).toBeVisible();
  await p.getByLabel("Archetype").selectOption("Loner");
  await p.getByLabel("Sect").selectOption("Camarilla");
  await expect(p.getByLabel("Sect")).toHaveValue("Camarilla");
  await p.waitForTimeout(500);
  await card(p, "Concept").screenshot(shot("wizard-concept"));

  // Every pick placed: the Review step, ready to finish.
  await placePicks(p, theo);
  await p.goto(`/characters/${theo}/create/review`);
  await expect(p.getByText("Everything is placed. After finishing, new dots come from experience.")).toBeVisible();
  await card(p, "Review").screenshot(shot("wizard-review"));

  // Lucian, built for the troupe and accepted by it, with XP from a game.
  const { id: lucian } = await send(p, "POST", "/api/characters", { splat: "vampire", name: "Lucian Marsh", building_troupe_id: troupeId });
  await send(p, "PUT", `/api/characters/${lucian}/traits`, { category: "clan", name: "Brujah", rating: null });
  await send(p, "PUT", `/api/characters/${lucian}/traits`, { category: "archetype", name: "Loose Cannon", rating: null });
  await send(p, "PUT", `/api/characters/${lucian}/traits`, { category: "sect", name: "Camarilla", rating: null });
  await placePicks(p, lucian);
  await send(p, "POST", `/api/characters/${lucian}/creation/complete`);
  const asked = await send(p, "POST", `/api/characters/${lucian}/home-troupe`, { troupe_id: troupeId });
  await send(l, "POST", `/api/approvals/${asked.id}/approve`, {});
  await send(l, "POST", `/api/characters/${lucian}/xp`, { amount: 20, reason: "Game, 3 October" });

  // The sheet.
  await p.goto(`/characters/${lucian}`);
  await expect(card(p, "Experience")).toBeVisible();
  await expect(p.getByRole("heading", { name: "Disciplines", exact: true })).toBeVisible();
  await p.waitForTimeout(500);
  await p.screenshot({ ...shot("sheet"), clip: { x: 0, y: 0, width: 1280, height: 900 }, fullPage: true });

  // A discipline opened to its powers.
  const disciplines = card(p, "Disciplines");
  await disciplines.getByRole("button", { name: "Celerity", exact: true }).click();
  await expect(disciplines.getByText(/Alacrity/)).toBeVisible();
  await disciplines.screenshot(shot("trait-details"));
  await disciplines.getByRole("button", { name: "Celerity", exact: true }).click();

  // The cart: a skill raised, and a discipline dot that waits on the home troupe.
  await p.getByRole("button", { name: "Raise Dodge" }).click();
  await p.getByRole("button", { name: "Raise Celerity" }).click();
  const cart = card(p, "Cart");
  await expect(cart.getByText("Needs approval")).toBeVisible({ timeout: 20_000 });
  await expect(cart.getByRole("button", { name: "Spend XP" })).toBeEnabled();
  await p.waitForTimeout(500);
  // From the Experience card down to the foot of the cart.
  const top = (await card(p, "Experience").boundingBox())!;
  const foot = (await cart.boundingBox())!;
  const scrolled = await p.evaluate(() => window.scrollY);
  await p.screenshot({ ...shot("cart"), fullPage: true, clip: { x: top.x - 8, y: top.y + scrolled - 8, width: top.width + 16, height: foot.y + foot.height - top.y + 16 } });
  await cart.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText(/Some of it waits for the home troupe's approval/)).toBeVisible({ timeout: 20_000 });
  const troupes = card(p, "Troupes");
  await expect(troupes.getByText("Waiting for the home troupe to approve.", { exact: false })).toBeVisible();
  await troupes.screenshot(shot("waiting-approval"));

  // Sabine, kept in the vault, asks the troupe to be her home: a price to settle.
  const { id: sabine } = await send(p, "POST", "/api/characters", { splat: "vampire", name: "Sabine Okafor" });
  await send(p, "PUT", `/api/characters/${sabine}/traits`, { category: "clan", name: "Toreador", rating: null });
  await send(p, "PUT", `/api/characters/${sabine}/traits`, { category: "sect", name: "Camarilla", rating: null });
  await placePicks(p, sabine);
  await send(p, "POST", `/api/characters/${sabine}/creation/complete`);
  await send(p, "PUT", `/api/characters/${sabine}/traits`, { category: "skills", name: "Brawl", rating: 5 });
  await p.goto(`/characters/${sabine}/troupes`);
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: "Court of Ashes" });
  await expect(p.getByText("This troupe's rules differ from what you built with.")).toBeVisible();
  await p.getByLabel("A note for the storytellers").fill("Sabine is new to the city; happy to talk through her story.");
  const home = card(p, "Home troupe");
  await home.screenshot(shot("home-troupe"));
  await home.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText("Waiting for Court of Ashes's storytellers to accept this character.")).toBeVisible();

  // The backstory editor, with a draft saved.
  await p.goto(`/characters/${lucian}/backstory`);
  await p.getByRole("button", { name: "Write the backstory" }).click();
  await p.getByRole("button", { name: "Markdown", exact: true }).click();
  await p
    .getByLabel("Your backstory, in Markdown")
    .fill(
      "## Before the Embrace\n\nLucian ran a print shop near the docks, turning out pamphlets for every cause that paid.\n\n## The night it changed\n\nA customer who never came by day asked for one last job, and paid in a way Lucian did not expect.",
    );
  await expect(p.getByText(/^Saved \d/)).toBeVisible({ timeout: 15_000 });
  await card(p, "Backstory").screenshot(shot("backstory-editor"));
  await p.getByRole("button", { name: "Submit the backstory" }).click();
  await expect(p.getByRole("button", { name: "Edit the backstory" })).toBeVisible();

  // A downtime cycle opens; Lucian's form, part filled.
  const now = Date.now();
  const closes = new Date(now + 7 * 86400e3);
  closes.setHours(23, 0, 0, 0);
  const cycle = await send(l, "POST", `/api/troupes/${troupeId}/cycles`, {
    name: "Autumn nights",
    closes_at: closes.toISOString(),
    grace_ends_at: new Date(closes.getTime() + 2 * 86400e3).toISOString(),
  });
  await send(l, "POST", `/api/cycles/${cycle.id}/open`);

  // The Characters page, with where each stands.
  await p.goto("/characters");
  await expect(p.getByText(/^Downtime due/)).toBeVisible();
  await p.waitForTimeout(500);
  await p.locator("main").screenshot(shot("characters"));

  await p.goto(`/characters/${lucian}/downtime`);
  await expect(card(p, "Feeding")).toBeVisible();
  await p.getByLabel("Where and how").fill("The night market by the river");
  // Each action's keyword first: a Feed action is a feeding action (#509).
  await p.getByRole("button", { name: /^Add an action/ }).first().click();
  await p.getByRole("radio", { name: /^Feed/ }).click();
  await p.getByRole("textbox", { name: "Downtime action" }).first().fill("Hunt the night market by the river.");
  await p.getByRole("button", { name: /^Add an action/ }).first().click();
  await p.getByRole("radio", { name: /^Investigate/ }).click();
  await p.getByLabel("Or something else").fill("The old print shop");
  await p.getByRole("textbox", { name: "Downtime action" }).nth(1).fill("Ask around the docks about who bought the old print shop.");
  await expect(p.getByText(/^Saved \d/)).toBeVisible({ timeout: 15_000 });
  await p.locator("main").screenshot(shot("downtime"));
  await p.getByRole("button", { name: "Submit downtime" }).click();
  await expect(p.getByText(/^Submitted. You can keep editing until .+\.$/)).toBeVisible();

  // The results arrive.
  await send(l, "POST", `/api/cycles/${cycle.id}/close`, { add_to_ceiling: true });
  const responses: { id: string; character_name?: string }[] = await send(l, "GET", `/api/cycles/${cycle.id}/responses`);
  for (const response of responses)
    await send(l, "PUT", `/api/responses/${response.id}`, {
      body: "The shop was bought by a holding company in the Heights. Its lawyer only takes meetings after dark.",
    });
  await send(l, "POST", `/api/cycles/${cycle.id}/deliver`, { partial: true });
  await p.goto(`/characters/${lucian}/results`);
  await expect(p.getByText(/holding company in the Heights/)).toBeVisible();
  await p.locator("main").screenshot(shot("results"));

  // Games: one coming up, answered, and one tonight with check-in open.
  const soon = new Date(now + 14 * 86400e3);
  soon.setHours(19, 0, 0, 0);
  await send(l, "POST", `/api/troupes/${troupeId}/games`, { starts_at: soon.toISOString(), ends_at: new Date(soon.getTime() + 5 * 3600e3).toISOString() });
  // Tonight at seven where check-in can open for it (from 12 hours before), else an hour ago.
  const seven = new Date(now);
  seven.setHours(19, 0, 0, 0);
  const start = seven.getTime() - now < 12 * 3600e3 && now - seven.getTime() < 4 * 3600e3 ? seven : new Date(now - 3600e3);
  const tonight = await send(l, "POST", `/api/troupes/${troupeId}/games`, { starts_at: start.toISOString(), ends_at: new Date(start.getTime() + 5 * 3600e3).toISOString() });
  const { checkin } = await send(l, "PUT", `/api/troupes/${troupeId}/games/${tonight.id}/checkin`);
  await p.goto(`/troupes/${troupeId}`);
  const games = card(p, "Games");
  await games.getByRole("group", { name: /^Are you coming on/ }).last().getByRole("button", { name: "Coming", exact: true }).click();
  await expect(games.getByRole("button", { name: "Coming", exact: true, pressed: true })).toBeVisible();
  await games.screenshot(shot("games"));

  // Check-in at the door, from its code.
  await p.goto(`/check-in/${checkin.code}`);
  await expect(p.getByText("Who are you playing tonight?")).toBeVisible();
  await p.getByRole("radio", { name: "Lucian Marsh" }).check();
  await p.locator("main section").first().screenshot(shot("check-in"));
  await p.getByRole("button", { name: "Check in Lucian Marsh" }).click();

  // The Play View's Tracker, a few taps into the night.
  await expect(p.getByRole("heading", { name: "Lucian Marsh" })).toBeVisible();
  await p.goto(`/play/characters/${lucian}?tab=tracker`);
  await p.getByRole("button", { name: "Spend Blood" }).click();
  await p.getByRole("button", { name: "Spend Blood" }).click();
  await p.getByRole("button", { name: "Spend Willpower" }).click();
  await p.getByRole("button", { name: "+ Normal" }).click();
  await expect(p.getByText("Every tap shows here", { exact: false })).toHaveCount(0);
  // Let the toasts go.
  await expect(p.getByText(/^Took 1 normal/)).toBeHidden({ timeout: 30_000 });
  await p.screenshot({ ...shot("play-tracker"), clip: { x: 0, y: 0, width: 1280, height: 860 }, fullPage: true });

  // Retiring, from the ⋯ menu.
  await p.goto(`/characters/${lucian}`);
  await p.getByRole("button", { name: "More for Lucian Marsh" }).click();
  await p.getByRole("menuitem", { name: "Retire…" }).click();
  const dialog = p.getByRole("dialog", { name: "Retire Lucian Marsh" });
  await dialog.getByRole("radio", { name: /^Off-field/ }).check();
  await dialog.screenshot(shot("retire"));
});
