import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, backstoryOptional, characterTab } from "./support";

/** Downtime: a troupe's whole month, and feeding in a downtime. */

closeContextsAfterEach();

/** How many pages a PDF that Chromium printed has, and the first one's size in points. */
function pdfPages(pdf: Buffer): { count: number; size: string } {
  const text = pdf.toString("latin1");
  const box = text.match(/\/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]/)!;
  return { count: text.match(/\/Type \/Page\b/g)?.length ?? 0, size: `${Math.round(Number(box[1]))} × ${Math.round(Number(box[2]))}` };
}

/**
 * One troupe's month, end to end: the custodian sets up a troupe, a player
 * builds a character and brings it to the troupe, the lead approves it and runs
 * a downtime cycle, a narrator answers an action, and the player reads the
 * results. Each person is a separate browser session.
 */
test("a troupe's month, from new character to downtime results", async ({ browser }) => {
  // The longest journey: the whole month, longer than the others, above all on a phone.
  test.slow();
  const custodian = await person(browser, "custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "lead");
  const narrator = await person(browser, "narrator");
  const player = await person(browser, "player");
  const troupeName = `Court of Ash ${run}`;

  // The custodian sets up the troupe.
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  await backstoryOptional(custodian.page, troupeName);

  // The lead adds a narrator.
  await lead.page.getByRole("link", { name: "Troupes" }).click();
  await lead.page.getByRole("link", { name: troupeName }).click();
  await lead.page.getByRole("link", { name: "Staff" }).click();
  await expect(lead.page.getByRole("heading", { name: "Add staff" })).toBeVisible();
  await lead.page.screenshot(shots("troupe-nav"));
  // Found by typing part of their handle, and picked from what comes up.
  await lead.page.getByLabel("Person").fill(narrator.handle.slice(0, -3));
  await lead.page.getByRole("option", { name: `@${narrator.handle}` }).click();
  await expect(lead.page.getByLabel("Person")).toHaveValue(narrator.handle);
  await lead.page.getByRole("button", { name: "Add to staff" }).click();
  await expect(lead.page.getByText(`@${narrator.handle} · Narrator`)).toBeVisible();

  // The player builds a character in the creation wizard, then buys Influence with XP.
  const p = player.page;
  await p.getByLabel("Name").fill("Agnes");
  // Built for the troupe from the start, so its rules and lists apply. (The page
  // loaded before the troupe existed.)
  await p.reload();
  await p.getByLabel("Name").fill("Agnes");
  await p.getByLabel("Which troupe will you play in?").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  await p.getByLabel("Clan").selectOption("Brujah");
  await expect(p.getByLabel("Clan")).toHaveValue("Brujah");
  // Only the Sabbat have a faction, and leaving the Sabbat drops it.
  await expect(p.getByLabel("Faction")).toHaveCount(0);
  await p.getByLabel("Sect").selectOption("Sabbat");
  await p.getByLabel("Faction").selectOption("Orthodox");
  await expect(p.getByLabel("Faction")).toHaveValue("Orthodox");
  await p.getByLabel("Sect").selectOption("Camarilla");
  await expect(p.getByLabel("Faction")).toHaveCount(0);
  // Saving a step reloads what can be taken, which can take several seconds on a busy server.
  const next = async (heading: string) => {
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
  };
  const tap = async (...dots: string[]) => {
    for (const dot of dots) await p.getByRole("button", { name: dot, exact: true }).click();
  };
  await next("Attributes");
  await tap("Physical 7", "Social 5", "Mental 3");
  await tap("Mental 7"); // swaps with Physical
  await expect(p.getByRole("button", { name: "Physical 3", exact: true })).toHaveAttribute("aria-pressed", "true");
  await next("Focuses");
  await tap("Strength 1", "Wits 1", "Charisma 1");
  await next("Skills");
  await tap("Brawl 4", "Dodge 3", "Athletics 3", "Awareness 2", "Empathy 2", "Firearms 2");
  await tap("Investigation 1", "Leadership 1", "Medicine 1", "Melee 1");
  await expect(p.getByRole("button", { name: "Stealth 3", exact: true })).toBeDisabled();
  // The one 4 greys out once used (only attributes swap), and Clear frees it again.
  await expect(p.getByRole("button", { name: "Stealth 4", exact: true })).toBeDisabled();
  await p.getByRole("button", { name: "Clear Brawl" }).click();
  await expect(p.getByRole("button", { name: "Stealth 4", exact: true })).toBeEnabled();
  await tap("Brawl 4");
  // At the foot of the list, what is left is still in view.
  await p.getByRole("button", { name: "Save and continue" }).scrollIntoViewIfNeeded();
  await expect(p.getByRole("list", { name: "Skills picks left" })).toBeInViewport();
  await p.screenshot(shots("creation"));
  await next("Backgrounds");
  // What each background is, a tap away.
  await p.getByRole("button", { name: "About Generation" }).click();
  await expect(p.getByText(/Every vampire needs at least 1 dot/)).toBeVisible();
  // A vampire cannot move on without Generation, nor skip ahead.
  await tap("Fame 3", "Herd 2");
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByText(/Before moving on: A vampire needs at least 1 dot of Generation/)).toBeVisible();
  await expect(p.getByRole("heading", { name: "Backgrounds", exact: true })).toBeVisible();
  await expect(p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Disciplines/ })).toHaveCount(0);
  await tap("Generation 1");
  await next("Disciplines");
  await expect(p.getByText("in-clan").first()).toBeVisible();
  await tap("Celerity 2", "Potence 1", "Presence 1");
  await next("Merits & flaws");
  // A quick pick shows the clan's merits. Only one clan merit of each value: ticking
  // Burning Wrath (2) greys out Iron Heart (2), with why; unticking frees it again.
  await p.getByRole("button", { name: "Brujah merits" }).click();
  await expect(p.getByRole("button", { name: "Brujah merits" })).toHaveAttribute("aria-pressed", "true");
  await p.getByRole("checkbox", { name: /^Burning Wrath/ }).check();
  await expect(p.getByRole("checkbox", { name: /^Iron Heart/ })).toBeDisabled();
  await expect(p.getByText(/Burning Wrath is already a clan merit of this value/)).toBeVisible();
  await p.getByRole("checkbox", { name: /^Burning Wrath/ }).uncheck();
  await expect(p.getByRole("checkbox", { name: /^Iron Heart/ })).toBeEnabled();
  // Clan merits are only for their clan: a Brujah sees Absent Sway barred, with the reason.
  await p.getByLabel("Show Merits").selectOption({ label: "For Toreador" });
  await p.getByLabel("Search Merits").fill("Absent Sway");
  await expect(p.getByText(/Absent Sway is only for Toreador/)).toBeVisible();
  await p.getByLabel("Show Merits").selectOption({ label: "What this character can take" });
  await p.getByLabel("Search Merits").fill("Acute");
  await p.getByLabel(/Acute Sense/).check();
  await next("Review");
  await p.screenshot(shots("review"));
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  // Health is boxes to tick, like the paper sheet: three of each to start, and no dots.
  await expect(part("Health Levels").getByText("Incapacitated characters lose their simple action.")).toBeVisible();
  for (const level of ["Healthy", "Injured", "Incapacitated"])
    await expect(part("Health Levels").getByRole("img", { name: `${level}: 3 boxes` })).toBeVisible();
  await expect(part("Expended").getByText("Healthy")).toHaveCount(0);
  // Changes wait in the cart, with what each costs, until Spend XP.
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  await part("Backgrounds").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Backgrounds").fill("Elite");
  await p.getByRole("button", { name: "Influences: The Elite" }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await expect(cart.getByText("Add Influences: The Elite 1 · 1 XP")).toBeVisible();
  // A focus can be changed after creation, for 10 XP.
  await p.getByRole("listitem").filter({ hasText: "Strength" }).getByRole("button", { name: "Change" }).click();
  await p.getByLabel("Change Strength to").selectOption("Dexterity");
  await p.getByRole("button", { name: "Add to cart · 10 XP" }).click();
  await expect(cart.getByText("Strength → Dexterity · 10 XP")).toBeVisible();
  await expect(p.getByText("after these changes", { exact: true })).toBeVisible();
  await expect(p.getByText("19", { exact: true })).toBeVisible(); // 30 − 1 for Influence − 10
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 11 XP.")).toBeVisible();
  await expect(p.getByText("Available", { exact: true })).toBeVisible();
  await expect(p.getByText("19", { exact: true })).toBeVisible();
  // Merits that give other traits apply them: Rugged adds a health level to each track.
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  // Every Ventrue merit, though Agnes is Brujah and cannot take them.
  await p.getByLabel("Show").selectOption({ label: "For Ventrue" });
  await expect(p.getByRole("button", { name: /Aura of Command/ })).toBeDisabled();
  await p.getByLabel("Show").selectOption({ label: "What this character can take" });
  await p.getByLabel("Search Merits").fill("Rugged");
  await p.getByRole("button", { name: /^Rugged/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("+1 from Rugged").first()).toBeVisible();
  await expect(p.getByText("16", { exact: true })).toBeVisible();
  for (const level of ["Healthy", "Injured", "Incapacitated"])
    await expect(part("Health Levels").getByRole("img", { name: `${level}: 4 boxes` })).toBeVisible();
  await p.screenshot(shots("sheet"));
  // A picture of Agnes, cropped to her face, shows at the top of her page.
  await p.getByRole("button", { name: "Add a picture of Agnes" }).click();
  await p.getByLabel("Choose a picture").setInputFiles("e2e/portrait.jpg");
  const portrait = p.getByRole("slider", { name: /Where the portrait is/ });
  await expect(portrait).toBeVisible();
  await p.getByLabel("Size").fill("60");
  await portrait.focus();
  for (let i = 0; i < 12; i++) await p.keyboard.press("ArrowUp");
  await p.screenshot(shots("crop"));
  await p.getByRole("button", { name: "Save picture" }).click();
  await expect(p.getByRole("dialog")).toBeHidden();
  await expect(p.getByRole("button", { name: "Change Agnes's picture" }).locator('img[src*="/pictures/"]')).toBeVisible();
  await p.screenshot(shots("picture"));
  // The character's own log says when, who and what.
  await characterTab(p, "Log");
  await expect(p.getByText("bought Influences: The Elite 1 for Agnes (1 XP).", { exact: false })).toBeVisible();

  // …and asks to make the troupe its home.
  await characterTab(p, "Troupes");
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: troupeName });
  await expect(p.getByText("Nothing differs")).toBeVisible();
  await expect(p.getByText(/If accepted now, 11 XP will be lost/)).toBeVisible();
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(/Waiting for .* storytellers/)).toBeVisible();

  // The lead's bell says so, and leads straight to the troupe's approvals, whose tab counts it too.
  await lead.page.reload();
  await lead.page.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await lead.page.screenshot(shots("bell"));
  await lead.page.getByRole("button", { name: /Agnes asks to make Court of Ash .* its home/ }).click();
  await expect(lead.page.getByRole("link", { name: /Approvals/ }).getByLabel("1 waiting")).toBeVisible();
  await expect(lead.page.getByText("asking to make this home")).toBeVisible();
  await lead.page.screenshot(shots("approvals"));
  await lead.page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(lead.page.getByText("Nothing pending.")).toBeVisible();

  // Accepted, Agnes keeps only 5 of her unspent creation XP. Her storytellers award her some.
  await lead.page.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  const agnesRow = lead.page.getByRole("listitem").filter({ has: lead.page.getByRole("link", { name: "Agnes", exact: true }) });
  await expect(agnesRow.getByText(/ · (Neonate|Ancilla|Elder)$/)).toBeVisible();
  await expect(agnesRow.locator('img[src*="/pictures/"]')).toBeVisible();
  await lead.page.screenshot(shots("roster"));
  await lead.page.getByRole("button", { name: "Award XP to Agnes" }).click();
  await lead.page.getByLabel("XP for Agnes").fill("10");
  await lead.page.getByLabel("Reason for Agnes's XP").fill("First game");
  await lead.page.getByRole("button", { name: "Award", exact: true }).click();
  await expect(lead.page.getByRole("dialog")).toBeHidden();

  // A game's XP for everyone at once, starting at the troupe's usual 8.
  await lead.page.locator("main").getByRole("link", { name: "Award XP", exact: true }).click();
  await expect(lead.page.getByLabel("XP for Agnes", { exact: true })).toHaveValue("8");
  await lead.page.getByRole("button", { name: "More XP for Agnes" }).click();
  await lead.page.getByLabel("Note everyone gets").fill("Game, 18 October");
  await lead.page.getByRole("button", { name: "Award…" }).click();
  await lead.page.screenshot(shots("bulk-xp"));
  await lead.page.getByRole("button", { name: "Yes, award 9 XP" }).click();
  await expect(lead.page.getByText("Awarded 9 XP to 1 character for “Game, 18 October”.")).toBeVisible();
  // The everyone amount also raised the troupe's XP floor and ceiling.
  await expect(lead.page.getByText("The floor and ceiling went up by 8.", { exact: false })).toBeVisible();

  // Once accepted, a discipline dot waits on the home troupe, with the XP held.
  await characterTab(p, "Sheet");
  await p.getByRole("button", { name: "Raise Celerity" }).click();
  await expect(cart.getByText("Celerity 2 → 3 · 9 XP")).toBeVisible();
  await expect(cart.getByText("needs approval")).toBeVisible();
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Some of it waits for the home troupe's approval.")).toBeVisible();
  await expect(p.getByText("awaiting approval").first()).toBeVisible();
  await lead.page.getByRole("link", { name: /Approvals/ }).click();
  await expect(lead.page.getByText(/Celerity 2 → 3, for 9 XP/)).toBeVisible();
  await lead.page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(lead.page.getByText("Nothing pending.")).toBeVisible();
  await p.reload();
  await expect(p.getByText("awaiting approval")).toHaveCount(0);

  // The troupe's characters and log show what happened.
  await lead.page.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await expect(lead.page.getByText("home", { exact: true })).toBeVisible();
  // Ticked characters print together, in a new tab, from the Print… menu.
  await lead.page.getByRole("button", { name: "Print…" }).click();
  await expect(lead.page.getByRole("button", { name: "Print selected (0)" })).toBeDisabled();
  await lead.page.getByLabel("Select Agnes").check();
  const printTab = lead.page.context().waitForEvent("page");
  await lead.page.getByRole("button", { name: "Print selected (1)" }).click();
  const printed = await printTab;
  await expect(printed.getByText("1 sheet", { exact: true })).toBeVisible();
  await expect(printed.getByText("Agnes", { exact: true }).first()).toBeVisible();
  await printed.close();

  // The troupe page has Characters and Players groups: NPCs and At game sit under Characters,
  // and Players lists the player with their character, linking to their profile.
  const sections = lead.page.getByRole("navigation", { name: "Troupe sections" });
  await expect(sections.getByRole("link", { name: "Players", exact: true })).toBeVisible();
  await expect(sections.getByRole("link", { name: "People", exact: true })).toHaveCount(0);
  const characterTabs = lead.page.getByRole("navigation", { name: "Characters", exact: true });
  for (const tab of ["NPCs", "At game", "Award XP", "Approvals"]) await expect(characterTabs.getByRole("link", { name: tab })).toBeVisible();
  await sections.getByRole("link", { name: "Players", exact: true }).click();
  const playerRow = lead.page.getByRole("listitem").filter({ has: lead.page.getByRole("link", { name: /^player @/ }) }).first();
  await expect(playerRow.getByRole("link", { name: "Agnes", exact: true })).toBeVisible();
  await expect(playerRow.getByText("Home", { exact: true })).toBeVisible();
  await lead.page.getByLabel("Search players").fill("nobody by this name");
  await expect(lead.page.getByText("No players match.")).toBeVisible();
  await lead.page.getByLabel("Search players").fill("agnes");
  await lead.page.screenshot(shots("players"));
  await playerRow.getByRole("link", { name: /^player @/ }).click();
  await expect(lead.page).toHaveURL(/\/players\//);
  await lead.page.goBack();
  await sections.getByRole("link", { name: "Characters", exact: true }).click();

  // Game badges. The custodian adds a logo for Agnes's clan (Horatio ships none)…
  await custodian.page.getByRole("link", { name: "Custodian", exact: true }).click();
  await custodian.page.getByRole("link", { name: "Clan logos" }).click();
  await custodian.page.getByLabel("Search clans").fill("Brujah");
  await custodian.page.getByLabel("Logo for Brujah", { exact: true }).setInputFiles("e2e/clan-logo.png");
  await expect(custodian.page.getByRole("img", { name: "Brujah logo" })).toBeVisible();
  await custodian.page.screenshot(shots("clan-logos"));
  // …the lead notes what others notice about her, and prints the badges of everyone ticked.
  await lead.page.getByRole("link", { name: "Agnes", exact: true }).click();
  await lead.page.getByRole("button", { name: "Badge", exact: true }).click();
  await lead.page.getByLabel("Also shown on the badge").fill("Smells faintly of brine");
  await lead.page.getByRole("button", { name: "Save note" }).click();
  await expect(lead.page.getByRole("dialog")).toBeHidden();
  await lead.page.goBack();
  await lead.page.getByLabel("Select Agnes").check();
  await lead.page.getByRole("button", { name: "Print… (1 selected)" }).click();
  const badgeTab = lead.page.context().waitForEvent("page");
  await lead.page.getByRole("button", { name: "Badges for selected (1)" }).click();
  const badges = await badgeTab;
  const badge = badges.getByRole("article", { name: "Badge for Agnes" });
  await expect(badge.getByText("Brujah · Neonate")).toBeVisible();
  const band = badge.getByRole("list", { name: "What others can see" });
  await expect(band).toHaveText("Smells faintly of brine");
  await expect(badge.getByRole("img", { name: "Brujah logo" })).toBeVisible();
  await expect(badge.locator('img[src$="/portrait.jpg"]')).toBeVisible();
  // White, the troupe's name on the bottom line, the visible traits centred in their band.
  await expect(badge).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(badge.getByText(troupeName)).toBeVisible();
  await expect(band).toHaveCSS("text-align", "center");
  await expect(band).toHaveCSS("justify-content", "center");
  await badges.screenshot(shots("badges"));
  await badges.getByLabel("Black and white").check();
  await badges.screenshot(shots("badges-plain"));
  if (test.info().project.name === "desktop") {
    await badges.emulateMedia({ media: "print" });
    const pdf = await badges.pdf({ path: "test-results/screens/badges.pdf", preferCSSPageSize: true, printBackground: true });
    expect(pdfPages(pdf)).toEqual({ count: 1, size: "612 × 792" });
    await badges.emulateMedia({ media: "screen" });
  }
  // Four sizes, for common badge holders, as many to the paper as fit; the
  // contents scale to each, the troupe's name still on the bottom line.
  await expect(badges.getByText("1 badge · four to each US Letter page")).toBeVisible();
  for (const [size, perPage, inches, shot] of [
    ["3 × 4 in", "four", 3, "3x4"],
    ["ID card, 2.25 × 3.5 in", "nine", 2.25, "cr80"],
    ["4 × 6 in", "two", 4, "4x6"],
  ] as const) {
    await badges.getByLabel("Size").selectOption({ label: size });
    await expect(badges.getByText(`1 badge · ${perPage} to each US Letter page`)).toBeVisible();
    expect((await badge.boundingBox())!.width).toBeCloseTo(inches * 96, 0);
    await expect(badge.getByText(troupeName)).toBeVisible();
    expect(await badge.evaluate((card) => card.scrollHeight - card.clientHeight)).toBeLessThanOrEqual(1);
    await badges.screenshot(shots(`badges-${shot}`));
  }
  await badges.close();
  // Each person's paper and badge size are settings: badges open at that size.
  const characters = lead.page.url();
  await lead.page.goto("/account/settings");
  for (const [setting, choice] of [
    ["Paper", "A4"],
    ["Badge size", "3 × 4 in"],
  ] as const) {
    const saved = lead.page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.ok());
    await lead.page.getByRole("radiogroup", { name: setting }).getByRole("radio", { name: choice }).click();
    await saved;
  }
  await lead.page.goto(characters);
  await lead.page.getByRole("button", { name: "Print…" }).click();
  const staffTab = lead.page.context().waitForEvent("page");
  await lead.page.getByRole("button", { name: "Storyteller badges" }).click();
  const staffBadges = await staffTab;
  await expect(staffBadges.getByLabel("Size")).toHaveValue("3x4");
  await expect(staffBadges.getByText("2 badges · four to each A4 page")).toBeVisible();
  await expect(staffBadges.getByRole("article", { name: "Badge for lead" }).getByText("Lead Storyteller")).toBeVisible();
  await expect(staffBadges.getByRole("article", { name: "Badge for narrator" }).getByText("Narrator", { exact: true })).toBeVisible();
  await expect(staffBadges.getByRole("article", { name: "Badge for lead" }).getByText(troupeName)).toBeVisible();
  await staffBadges.screenshot(shots("staff-badges"));
  await staffBadges.close();
  await lead.page.getByRole("link", { name: "Troupe", exact: true }).click();
  await lead.page.getByRole("link", { name: "Log", exact: true }).click();
  await expect(lead.page.getByText("lead accepted Agnes (player); this is its home.")).toBeVisible();
  await expect(lead.page.getByText("Agnes (player) joined the troupe.")).toBeVisible();
  await expect(lead.page.getByText(/lead approved Agnes \(player\)'s Celerity/)).toBeVisible();
  await lead.page.screenshot(shots("log"));
  // The troupe's rules: the lead can play a check differently.
  await lead.page.getByRole("link", { name: "Customise", exact: true }).click();
  await lead.page.getByRole("link", { name: "Rules", exact: true }).click();
  await lead.page.getByLabel("Search checks").fill("Calm Heart");
  await lead.page.getByLabel(/Setting for: Brujah cannot take Calm Heart/).selectOption({ label: "Allow, for our review" });
  await expect(lead.page.getByRole("button", { name: "House rules (1)" })).toBeVisible();
  await lead.page.screenshot(shots("rules"));
  // …and set its own price: Generation 1 skills at a flat 1 XP a dot, which Agnes pays.
  await lead.page.getByRole("link", { name: "Costs", exact: true }).click();
  await lead.page.getByRole("button", { name: "Change the price for All Skills, Generation background 1" }).click();
  await lead.page.getByLabel("How it's priced").selectOption({ label: "The same for each dot" });
  await lead.page.getByLabel("XP per dot").fill("1");
  await lead.page.getByLabel("Note for players").fill("Skills come easily here");
  await expect(lead.page.getByRole("row", { name: "As written 1 3 6 10 15" })).toBeVisible();
  await expect(lead.page.getByRole("row", { name: "With the change 1 2 3 4 5" })).toBeVisible();
  await lead.page.screenshot(shots("costs"));
  await lead.page.getByRole("button", { name: "Save price" }).click();
  await expect(lead.page.getByText("replaced here")).toBeVisible();
  // A fixed price for a merit held at one rating is its value here, which the editor says.
  await lead.page.getByRole("button", { name: "Add a price" }).click();
  await lead.page.getByLabel("Category").selectOption({ label: "Merits" });
  await lead.page.getByLabel("Trait").fill("Talisman");
  await lead.page.getByLabel("How it's priced").selectOption({ label: "One price, whatever the rating" });
  await expect(lead.page.getByText("Talisman is always held at one rating (3 by the book).", { exact: false })).toBeVisible();
  await lead.page.getByRole("button", { name: "Cancel" }).click();
  await characterTab(p, "Sheet");
  await p.getByRole("button", { name: "Raise Investigation" }).click();
  // Until it is spent, the sheet shows what the rating would become.
  const investigation = p.locator("li", { has: p.getByRole("button", { name: "Raise Investigation" }) });
  await expect(investigation.getByLabel("1 dots, 2 after the changes in the cart")).toHaveText("1 → 2");
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 1 XP.")).toBeVisible();
  await expect(investigation.getByLabel("2 dots", { exact: true })).toHaveText("2");
  await characterTab(p, "Log");
  await expect(p.getByText("raised Agnes's Investigation from 1 to 2 (1 XP).", { exact: false })).toBeVisible();

  // The troupe lists the areas its Elite influence covers; Agnes picks one.
  await lead.page.getByRole("link", { name: "Customise", exact: true }).click();
  await lead.page.getByRole("link", { name: "Specialisations", exact: true }).click();
  await lead.page.getByRole("navigation", { name: "Backgrounds" }).getByRole("link", { name: "Influence: Elite" }).click();
  await expect(lead.page).toHaveURL(/\/specializations\/influence-elite$/);
  await lead.page.screenshot(shots("troupe-specializations"));
  const elite = lead.page.locator("section").filter({ has: lead.page.getByRole("heading", { name: "Influence: Elite", exact: true }) });
  await elite.getByRole("button", { name: "Make our own list" }).click();
  await elite.getByLabel("Influence: Elite, one per line").fill("Police\nFinance");
  await elite.getByRole("button", { name: "Save our list" }).click();
  await expect(elite.getByText("Finance, Police")).toBeVisible();
  await characterTab(p, "Sheet");
  await p.reload(); // to see the list the lead has just set
  await p.getByRole("button", { name: "Add to Influence: Elite" }).click();
  await p.getByRole("button", { name: "Police", exact: true }).click();
  await expect(p.getByRole("button", { name: "Remove Police" })).toBeVisible();
  // Contacts, named freely: one per dot.
  await part("Backgrounds").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Backgrounds").fill("Contacts");
  await p.getByRole("button", { name: /^Contacts/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await p.getByRole("button", { name: "Spend XP" }).click();
  await p.getByRole("button", { name: "Add to Contacts Specializations" }).click();
  const contact = p.getByRole("listitem").filter({ has: p.getByLabel("Name a Contacts Specializations") });
  await contact.getByLabel("Name a Contacts Specializations").fill("Reyes");
  await contact.getByRole("button", { name: "Add", exact: true }).click();
  await expect(p.getByRole("button", { name: "Remove Reyes" })).toBeVisible();
  await p.screenshot(shots("specializations"));

  // The lead runs a cycle.
  await lead.page.getByRole("link", { name: "Downtimes", exact: true }).click();
  await expect(lead.page.getByRole("heading", { name: "New cycle" })).toBeVisible();
  await lead.page.getByLabel("Name").fill("November");
  await lead.page.getByRole("button", { name: "Create draft" }).click();
  await lead.page.getByRole("link", { name: "November" }).click();
  await lead.page.getByRole("button", { name: "Open for submissions" }).click();
  await expect(lead.page.getByText("0 of 1 submitted")).toBeVisible();

  // The player answers and submits. The deadline shows with its zone, so everyone agrees on it.
  await characterTab(p, "Downtime");
  await expect(p.getByText(/^Due [A-Z][a-z]{2} \d{1,2} [A-Z][a-z]{2}( \d{4})?, \d{1,2}:\d{2} [ap]m \S+$/)).toBeVisible();
  await p.getByRole("button", { name: /Add an action/ }).first().click();
  await p.getByLabel("Downtime action").fill("Hunt along the river docks.");
  // An influence action is named. Agnes's own Police specialisation lets her Elite 1 reach a level-2 action.
  const influence = p.locator("section").filter({ has: p.getByRole("heading", { name: "Elite influence action" }) });
  await influence.getByRole("button", { name: /Add an action/ }).click();
  await influence.getByLabel("Elite influence action").fill("Ask around the precinct about the missing ledger.");
  const action = influence.getByLabel("Action", { exact: true });
  await expect(action.locator("option", { hasText: "Gossip and Insider Trading" })).toHaveCount(0);
  await influence.getByLabel("Specialisation").selectOption("Police");
  await action.selectOption({ label: "2: Gossip and Insider Trading" });
  await expect(influence.getByText("Your Police specialisation counts your Elite as 2 for this.")).toBeVisible();
  await p.screenshot(shots("downtime"));
  await p.getByRole("button", { name: "Submit downtime" }).click();
  await expect(p.getByText("submitted", { exact: true })).toBeVisible();

  // The lead hands the action to the narrator, who writes it. Staff see the influence action by name.
  await lead.page.getByRole("link", { name: "Responses" }).click();
  await expect(lead.page.getByText("2: Gossip and Insider Trading (Police)")).toBeVisible();
  // The lead logs it in the troupe's influence log, its purpose trimmed from the answer.
  await lead.page.getByRole("button", { name: "Log it" }).click();
  await expect(lead.page.getByLabel("Purpose")).toHaveValue("Ask around the precinct about the missing ledger.");
  await lead.page.getByLabel("Purpose").fill("To hear about the missing ledger");
  await lead.page.getByRole("button", { name: "Log it" }).click();
  await expect(lead.page.getByText("Logged as E1")).toBeVisible();
  await lead.page.getByLabel("Assign to").first().selectOption({ label: "narrator (Narrator)" });
  await expect(lead.page.getByLabel("Assign to").first()).not.toHaveValue("none");
  await narrator.page.getByRole("link", { name: "Troupes" }).click();
  await narrator.page.getByRole("link", { name: troupeName }).click();
  await narrator.page.getByRole("link", { name: "Downtimes", exact: true }).click();
  await narrator.page.getByRole("link", { name: "My work" }).click();
  // Each cycle says when it is due and what is left to write.
  await expect(narrator.page.getByRole("link", { name: "November" }).getByText(/^Due .* · 1 for you to write$/)).toBeVisible();
  await narrator.page.getByRole("link", { name: "November" }).click();
  await narrator.page.getByLabel("Response to Agnes").fill("The docks are crowded tonight; you feed well and unseen.");
  await narrator.page.getByRole("button", { name: "Save response" }).click();
  await expect(narrator.page.getByText("written", { exact: true })).toBeVisible();
  await narrator.page.screenshot(shots("narrator"));

  // The lead closes, told first what closing means while it isn't yet due.
  await lead.page.getByRole("link", { name: "Overview" }).click();
  await lead.page.getByRole("button", { name: "Close submissions" }).click();
  const closing = lead.page.getByRole("region", { name: "Close submissions?" });
  await expect(closing.getByText(/^It isn't due until /)).toBeVisible();
  await expect(closing.getByText("The 1 participant has submitted.")).toBeVisible();
  await lead.page.screenshot(shots("cycle-close"));
  await closing.getByRole("button", { name: "Yes, close submissions" }).click();
  await expect(lead.page.getByText("closed", { exact: true })).toBeVisible();

  // Delivering starts on the Delivery tab, which says what would go. Agnes's influence
  // action and her feeding are still unanswered, so by default nothing goes.
  await lead.page.getByRole("link", { name: "Deliver results" }).click();
  const deliverCard = lead.page.locator("section").filter({ has: lead.page.getByRole("heading", { name: "Deliver results" }) });
  await expect(deliverCard.getByText("0 of 1 downtime has every response written.")).toBeVisible();
  await expect(deliverCard.getByText("Agnes (1 of 3)")).toBeVisible();
  await expect(deliverCard.getByRole("button", { name: "Nothing to deliver" })).toBeDisabled();
  await deliverCard.getByLabel("Also deliver the 1 partly written, with what's written so far").check();
  await deliverCard.getByRole("button", { name: "Deliver 1 downtime" }).click();
  await expect(lead.page.getByText("Delivered 1 downtime.")).toBeVisible();
  // Each participant against each channel; with no connectors, in Horatio only.
  await expect(lead.page.getByRole("columnheader", { name: "In Horatio" })).toBeVisible();
  await expect(lead.page.getByRole("row", { name: /Agnes.*sent/ })).toBeVisible();
  await characterTab(p, "Results");
  await expect(p.getByText("you feed well and unseen")).toBeVisible();
  // New to the player, with the response under the action it answers.
  await expect(p.getByText("New", { exact: true })).toBeVisible();
  const answered = p.locator("section").filter({ hasText: "you feed well and unseen" }).last();
  await expect(answered.getByText("Your action")).toBeVisible();
  await expect(answered.getByText("Hunt along the river docks.")).toBeVisible();
  await p.screenshot(shots("results"));

  // The rest is answered after delivery: the downtime shows as changed, and goes again as an update.
  await lead.page.getByRole("link", { name: "Responses", exact: true }).click();
  await lead.page.getByRole("button", { name: /^unassigned \(1\)/i }).click();
  await lead.page.getByLabel("Response to Agnes").fill("The desk sergeant owes you a favour.");
  await lead.page.getByRole("button", { name: "Save response" }).click();
  await expect(lead.page.getByRole("button", { name: /^written \(2\)/i })).toBeVisible();
  await lead.page.getByRole("link", { name: "Feeding", exact: true }).click();
  await expect(lead.page.getByText("Already delivered: a change goes out as an update with the next delivery.")).toBeVisible();
  await lead.page.getByRole("button", { name: "Answer", exact: true }).click();
  await expect(lead.page.getByRole("button", { name: "Change answer" })).toBeVisible();
  await lead.page.getByRole("link", { name: "Delivery", exact: true }).click();
  await expect(lead.page.getByRole("row", { name: /Agnes/ }).getByText("changed since delivery")).toBeVisible();
  await expect(deliverCard.getByText("Agnes (update)")).toBeVisible();
  await lead.page.screenshot(shots("cycle-delivery"));
  await deliverCard.getByRole("button", { name: "Deliver 1 downtime" }).click();
  await expect(lead.page.getByText("Delivered 1 downtime, as an update.")).toBeVisible();
  await expect(lead.page.getByText("changed since delivery")).toHaveCount(0);
  await p.reload();
  await expect(p.getByText("The desk sergeant owes you a favour.")).toBeVisible();
  await expect(p.getByText("you feed well and unseen")).toBeVisible();
  // The update is new again, and says when it came.
  await expect(p.getByText(/^Updated \d/)).toBeVisible();
  await expect(p.getByText("New", { exact: true })).toBeVisible();

  // Marking the cycle complete says first that nothing is left.
  await lead.page.getByRole("link", { name: "Overview" }).click();
  await lead.page.getByRole("button", { name: "Mark complete" }).click();
  const completing = lead.page.getByRole("region", { name: "Mark complete?" });
  await expect(completing.getByText("Every response is written.")).toBeVisible();
  await expect(completing.getByText("Players have every result as it stands.")).toBeVisible();
  await completing.getByRole("button", { name: "Yes, mark complete" }).click();
  await expect(lead.page.getByText("complete", { exact: true })).toBeVisible();

  // Results always go out in Horatio; Discord needs the server set up first.
  await lead.page.getByRole("link", { name: "Troupes" }).click();
  await lead.page.getByRole("link", { name: troupeName }).click();
  await lead.page.getByRole("link", { name: "Customise", exact: true }).click();
  await lead.page.getByRole("link", { name: "Connectors", exact: true }).click();
  await expect(lead.page.getByText("always on")).toBeVisible();
  // In plain words, with no server settings named and nothing to fill in.
  await expect(lead.page.getByText(/Discord isn't set up on this server yet. Ask the custodian/)).toBeVisible();
  await expect(lead.page.getByText(/Email isn't set up on this server yet/)).toBeVisible();
  await expect(lead.page.getByText(/HORATIO_/)).toHaveCount(0);
  await expect(lead.page.getByRole("button", { name: "Save" })).toHaveCount(0);

  // The troupe's influence log: the logged answer, and an NPC's action logged by hand.
  await lead.page.getByRole("link", { name: "Downtimes", exact: true }).click();
  await lead.page.getByRole("link", { name: "Influence log", exact: true }).click();
  const e1 = lead.page.getByRole("listitem", { name: "Entry E1" });
  await expect(e1.getByText("To hear about the missing ledger")).toBeVisible();
  await expect(e1.getByText("Elite, Police · 2: Gossip and Insider Trading")).toBeVisible();
  await expect(e1.getByRole("link", { name: "Downtime: November" })).toBeVisible();
  await lead.page.getByRole("button", { name: "Log influence" }).click();
  const form = lead.page.getByRole("form", { name: "Log influence" });
  await form.getByLabel("Who").fill("REDACTED");
  await form.getByRole("option", { name: /^REDACTED/ }).click();
  await form.getByLabel("Type").selectOption({ label: "Underworld" });
  await form.getByLabel("Specialisation").selectOption("Transportation");
  await form.getByLabel("Action").selectOption({ label: "5: Lockdown" });
  await form.getByLabel("Purpose").fill("To secure the location of the gather");
  await form.getByRole("button", { name: "Log it" }).click();
  const uw1 = lead.page.getByRole("listitem", { name: "Entry UW1" });
  await expect(uw1.getByText("REDACTED")).toBeVisible();
  await expect(uw1.getByText("By hand")).toBeVisible();
  // Filtered to Underworld, only the NPC's action shows.
  await lead.page.getByLabel("Type", { exact: true }).selectOption({ label: "Underworld" });
  await expect(e1).toHaveCount(0);
  await expect(lead.page.getByText("1 entry, newest first.")).toBeVisible();
  await lead.page.screenshot(shots("influence-log"));
  // Edited, then deleted.
  await uw1.getByRole("button", { name: "Edit" }).click();
  const edit = lead.page.getByRole("form", { name: "Edit UW1" });
  await edit.getByLabel("Times taken").fill("3");
  await edit.getByRole("button", { name: "Save changes" }).click();
  await expect(uw1.getByText("logged 3 times")).toBeVisible();
  lead.page.once("dialog", (d) => d.accept());
  await uw1.getByRole("button", { name: "Delete" }).click();
  await expect(lead.page.getByText("No influence actions match these filters.")).toBeVisible();

  // The printable sheet, in the paper sheet's order.
  await characterTab(p, "Sheet");
  await p.getByRole("link", { name: "Print", exact: true }).click();
  await expect(p.getByText(/Home troupe: Court of Ash/)).toBeVisible();
  await expect(p.getByText("Brawl")).toBeVisible();
  // Health as on the paper sheet, with Rugged's extra box in each row.
  await expect(p.getByText("Incapacitated characters lose their simple action.")).toBeVisible();
  for (const level of ["Healthy", "Injured", "Incapacitated"])
    await expect(p.getByRole("img", { name: `${level}: 4 boxes` })).toBeVisible();
  // Specialisations in brackets after their trait, without dots or sections of their
  // own: a short list on the trait's line, a long one on a line under it.
  const specialised = async (page: Page) => {
    await expect(page.getByText("Contacts (Reyes)", { exact: true })).toBeVisible();
    await expect(page.getByText("Influences: The Elite", { exact: true })).toBeVisible();
    await expect(page.getByText("(Police)", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Specializations|Influence: Elite/ })).toHaveCount(0);
  };
  await specialised(p);
  // The whole page shows, scaled down on a phone to fit it; the paper size links to its setting.
  const paper = await p.locator("article").first().boundingBox();
  expect(paper!.width).toBeLessThanOrEqual(p.viewportSize()!.width);
  await expect(p.getByRole("link", { name: "For US Letter" })).toHaveAttribute("href", "/account/settings");
  await p.screenshot(shots("print"));
  if (test.info().project.name === "desktop") {
    await p.emulateMedia({ media: "print" });
    // On one page of US Letter, the paper Horatio starts on.
    const pdf = await p.pdf({ path: "test-results/screens/sheet.pdf", preferCSSPageSize: true });
    expect(pdfPages(pdf)).toEqual({ count: 1, size: "612 × 792" });
    await p.emulateMedia({ media: "screen" });
  }
  // Ratings print as numbers, and each attribute's focus sits beside it in brackets…
  await expect(p.getByText("Mental (Wits)")).toBeVisible();
  await expect(p.getByRole("img", { name: /dots$/ })).toHaveCount(0);
  // …or as pips, for one print, from the chevron beside Print.
  await p.goBack();
  await p.getByRole("button", { name: "Print with numbers or pips" }).click();
  await p.getByRole("menuitem", { name: "With pips" }).click();
  await expect(p.getByText("Mental (Wits)")).toBeVisible();
  await expect(p.getByRole("img", { name: "7 dots" }).first()).toBeVisible();
  await p.screenshot(shots("print-pips"));
  // Pips everywhere, from Settings: the Sheet tab shows them, and Print prints
  // them, with numbers now the chevron's choice.
  await p.goBack();
  const sheetPage = p.url();
  await p.goto("/account/settings");
  await Promise.all([
    p.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.ok()),
    p.getByRole("radiogroup", { name: "Show ratings as" }).getByRole("radio", { name: "Pips" }).click(),
  ]);
  await p.goto(sheetPage);
  await expect(p.getByRole("img", { name: "7 dots" }).first()).toBeVisible();
  // A change in the cart shows as outlined pips, not yet spent; Clear empties the cart.
  await p.getByRole("button", { name: "Raise Investigation" }).click();
  await expect(p.getByRole("img", { name: "2 dots, 3 after the changes in the cart" })).toBeVisible();
  await p.screenshot(shots("sheet-pips"));
  await p.getByRole("button", { name: "Clear" }).click();
  await expect(p.getByRole("img", { name: "2 dots, 3 after the changes in the cart" })).toHaveCount(0);
  await p.getByRole("link", { name: "Print", exact: true }).click();
  await expect(p.getByText("Mental (Wits)")).toBeVisible();
  await expect(p.getByRole("img", { name: "7 dots" }).first()).toBeVisible();
  await p.goBack();
  await p.getByRole("button", { name: "Print with numbers or pips" }).click();
  await p.getByRole("menuitem", { name: "With numbers" }).click();
  await expect(p.getByText("Mental (Wits)")).toBeVisible();
  await expect(p.getByRole("img", { name: /dots$/ })).toHaveCount(0);
  // The troupe's print view prints them the same way, as the lead's setting has
  // them: numbers.
  const troupeSheets = await lead.page.context().newPage();
  await troupeSheets.goto(`/print/troupes/${lead.page.url().match(/\/troupes\/([^/]+)/)![1]}`);
  await expect(troupeSheets.getByText("1 sheet", { exact: true })).toBeVisible();
  await specialised(troupeSheets);
  // On the lead's paper, A4, still one page to a sheet.
  await expect(troupeSheets.getByText("For A4")).toBeVisible();
  if (test.info().project.name === "desktop") {
    await troupeSheets.emulateMedia({ media: "print" });
    const pdf = await troupeSheets.pdf({ path: "test-results/screens/sheet-a4.pdf", preferCSSPageSize: true });
    expect(pdfPages(pdf)).toEqual({ count: 1, size: "595 × 842" });
  }
  await expect(troupeSheets.getByRole("img", { name: /dots$/ })).toHaveCount(0);
  await troupeSheets.close();
});

/**
 * Sharing out a cycle's responses (#376): they come by character, each folding
 * away; filtered by who has them; and several ticked are assigned in one go.
 */
test("staff share out a cycle's responses by character, and assign several in one go", async ({ browser }) => {
  const custodian = await person(browser, "bulkassign-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bulkassign-lead");
  const narrator = await person(browser, "bulkassign-narr");
  const players = [await person(browser, "bulkassign-ana"), await person(browser, "bulkassign-bo")];
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "GET" | "POST" | "PUT", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data: method === "GET" ? undefined : (data ?? {}) });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Bulk Assignment ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/staff`, { handle: narrator.handle, role: "narrator" });
  const picks: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  const ids: string[] = [];
  for (const [player, name] of [
    [players[0]!, "Clementine"],
    [players[1]!, "Barnaby"],
  ] as const) {
    const { id } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name });
    await send(player.page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    for (const [category, list] of Object.entries(picks))
      await send(player.page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send(player.page, "POST", `/api/characters/${id}/creation/complete`);
    const asked = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    ids.push(id);
  }
  const now = Date.now();
  const cycle = await send(lead.page, "POST", `/api/troupes/${troupe.id}/cycles`, {
    name: "Sharing month",
    closes_at: new Date(now + 7 * 86400e3).toISOString(),
    grace_ends_at: new Date(now + 9 * 86400e3).toISOString(),
  });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/open`);
  for (const [i, player] of players.entries()) {
    const form = await send(player.page, "GET", `/api/characters/${ids[i]}/downtime`);
    const question = form.questions.find((q: { prompt: string }) => q.prompt === "Downtime action");
    const answers = [1, 2].map((slot) => ({ question_id: question.id, slot, body: `Errand ${slot} for ${i ? "Barnaby" : "Clementine"}.` }));
    await send(player.page, "PUT", `/api/characters/${ids[i]}/downtime/answers`, { answers });
    await send(player.page, "POST", `/api/characters/${ids[i]}/downtime/submit`);
  }

  // The responses come by character, each with how many are written; one folds away.
  const l = lead.page;
  await l.goto(`/cycles/${cycle.id}/responses`);
  const clementine = l.getByRole("region", { name: "Clementine" });
  const barnaby = l.getByRole("region", { name: "Barnaby" });
  await expect(clementine.getByRole("button", { name: "Clementine 0 of 2 responses written" })).toBeVisible();
  await expect(barnaby.getByLabel("Response to Barnaby")).toHaveCount(2);
  await barnaby.getByRole("button", { name: /^Barnaby/ }).click();
  await expect(barnaby.getByLabel("Response to Barnaby")).toHaveCount(0);
  await barnaby.getByRole("button", { name: /^Barnaby/ }).click();
  await expect(barnaby.getByLabel("Response to Barnaby")).toHaveCount(2);
  // The assignment list names each staff member's role.
  await expect(l.getByLabel("Assign to").first().locator("option", { hasText: "bulkassign-narr (Narrator)" })).toHaveCount(1);

  // All of Clementine's and one of Barnaby's, to the narrator, in one go.
  await clementine.getByLabel("Select all of Clementine's").check();
  await barnaby.getByLabel("Select Barnaby: Downtime action").first().check();
  const bar = l.getByRole("form", { name: "Assign selected" });
  await expect(bar.getByText("3 selected")).toBeVisible();
  await bar.getByLabel("Assign selected to").selectOption({ label: "bulkassign-narr (Narrator)" });
  await l.screenshot(shots("responses-bulk"));
  await bar.getByRole("button", { name: "Assign 3" }).click();
  await expect(l.getByText("3 responses now with bulkassign-narr.")).toBeVisible();
  await expect(bar).toHaveCount(0);
  await expect(l.getByRole("button", { name: /^assigned \(3\)/i })).toBeVisible();

  // Filtered to the narrator's, the three show; the one left is still unassigned.
  await l.getByLabel("Who has it").selectOption({ label: "bulkassign-narr (Narrator)" });
  await expect(l.getByRole("textbox", { name: /^Response to / })).toHaveCount(3);
  await l.getByLabel("Who has it").selectOption({ label: "Unassigned" });
  await expect(l.getByRole("textbox", { name: /^Response to / })).toHaveCount(1);
  await expect(barnaby.getByLabel("Response to Barnaby")).toHaveCount(1);

  // The narrator has the three to write.
  const mine = await send(narrator.page, "GET", `/api/cycles/${cycle.id}/responses/mine`);
  expect(mine.map((m: { character_name: string }) => m.character_name)).toEqual(["Barnaby", "Clementine", "Clementine"]);
});

/**
 * Running a cycle: staff add a character accepted after it opened, find who
 * hasn't submitted, and remind them, which their player sees in the bell.
 */
test("staff add a character to an open cycle, filter to those not submitted, and remind them", async ({ browser }) => {
  const custodian = await person(browser, "dtchase-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "dtchase-lead");
  const ivy = await person(browser, "dtchase-ivy");
  const wren = await person(browser, "dtchase-wren");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "GET" | "POST" | "PUT", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data: method === "GET" ? undefined : (data ?? {}) });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupeName = `Chasing Court ${run}`;
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  /** A finished character whose home troupe this is. */
  const member = async (page: Page, name: string) => {
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
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id as string;
  };
  const ivyThorne = await member(ivy.page, "Ivy Thorne");
  const now = Date.now();
  const cycle = await send(lead.page, "POST", `/api/troupes/${troupe.id}/cycles`, {
    name: "Chase month",
    closes_at: new Date(now + 7.5 * 86400e3).toISOString(),
    grace_ends_at: new Date(now + 9.5 * 86400e3).toISOString(),
  });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/open`);
  await send(ivy.page, "POST", `/api/characters/${ivyThorne}/downtime/submit`);
  // Tobias is accepted after the cycle opened, so he isn't taking part yet.
  const tobias = await member(wren.page, "Tobias Wren");

  // The list of cycles says when each is due and how far it has got; the form
  // for the next waits behind a button while this one runs.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/downtimes`);
  const row = l.getByRole("link", { name: /Chase month/ });
  await expect(row.getByText(/^Due [A-Z][a-z]{2} \d{1,2} [A-Z][a-z]{2}( \d{4})? · 1 of 1 submitted$/)).toBeVisible();
  await expect(l.getByRole("heading", { name: "New cycle" })).toHaveCount(0);
  await expect(l.getByRole("button", { name: "New cycle" })).toBeVisible();
  await l.screenshot(shots("troupe-cycles"));
  await row.click();

  // The cycle keeps its troupe in view, and while open its progress is who has submitted.
  const trail = l.getByRole("navigation", { name: "Breadcrumb" });
  await expect(trail.getByRole("link", { name: troupeName })).toBeVisible();
  await expect(trail.getByRole("link", { name: "Downtimes" })).toHaveAttribute("href", `/troupes/${troupe.id}/downtimes`);
  await expect(l.getByText("1 of 1 submitted")).toBeVisible();
  await expect(l.getByRole("progressbar", { name: "Submitted" })).toBeVisible();
  await expect(l.getByText(/^7 days left · grace to [A-Z][a-z]{2} \d{1,2} [A-Z][a-z]{2}/)).toBeVisible();
  await expect(l.getByText("By who")).toHaveCount(0);
  await l.screenshot(shots("cycle-overview-open"));

  // Staff add Tobias from Participants.
  await l.getByRole("link", { name: "Participants" }).click();
  await expect(l.getByText("1 submitted", { exact: true })).toBeVisible();
  await l.getByRole("button", { name: "Add a character" }).click();
  const adding = l.getByRole("region", { name: "Add a character" });
  await adding.getByLabel("Character").selectOption({ label: `Tobias Wren (@${wren.handle})` });
  await adding.getByRole("button", { name: "Add to the cycle" }).click();
  await expect(l.getByText("Added Tobias Wren to Chase month.")).toBeVisible();
  await expect(l.getByText("1 submitted · 1 not started")).toBeVisible();
  await expect(l.getByRole("row", { name: new RegExp(`Tobias Wren.*@${wren.handle}.*not started`) })).toBeVisible();

  // Filtered to those not submitted, only Tobias is left; the overview links straight here.
  await l.getByRole("button", { name: "Not submitted (1)" }).click();
  await expect(l).toHaveURL(/participants\?show=not-submitted$/);
  await expect(l.getByRole("row", { name: /Tobias Wren/ })).toBeVisible();
  await expect(l.getByRole("row", { name: /Ivy Thorne/ })).toHaveCount(0);
  await l.getByRole("link", { name: "Overview" }).click();
  await l.getByRole("link", { name: "See who hasn't submitted" }).click();
  await expect(l.getByRole("button", { name: "Not submitted (1)" })).toHaveAttribute("aria-pressed", "true");

  // Reminding says first who it reaches.
  await l.getByRole("button", { name: "Remind those not submitted" }).click();
  const reminding = l.getByRole("region", { name: "Remind players?" });
  await expect(reminding.getByText("Remind 1 player?")).toBeVisible();
  await expect(reminding.getByText("Tobias Wren isn't submitted.")).toBeVisible();
  await l.screenshot(shots("cycle-participants-remind"));
  await reminding.getByRole("button", { name: "Yes, remind 1 player" }).click();
  await expect(l.getByText("Reminded 1 player.")).toBeVisible();
  await expect(l.getByText(/^Last reminded .* by dtchase-lead, 1 player\.$/)).toBeVisible();
  await l.getByRole("button", { name: "All (2)" }).click();
  await l.screenshot(shots("cycle-participants"));

  // Tobias's player has it in the bell, and it leads to his downtime.
  const w = wren.page;
  await w.reload();
  await w.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await w.getByRole("button", { name: /Tobias Wren's downtime for Chase month isn't submitted yet/ }).click();
  await expect(w).toHaveURL(new RegExp(`/characters/${tobias}/downtime$`));
});

/**
 * The player's writing is never lost: it saves itself once they stop typing, a
 * save that fails says so and keeps the text, a refetch while it is unsaved
 * leaves it be, and a removed action can be put back.
 */
test("a downtime keeps the player's writing: autosave, a failed save, a refetch, and Undo", async ({ browser }) => {
  const custodian = await person(browser, "dtkeep-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "dtkeep-lead");
  const player = await person(browser, "dtkeep-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "GET" | "POST" | "PUT", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data: method === "GET" ? undefined : (data ?? {}) });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Kept Words ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const { id } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: "Corvin" });
  await send(player.page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
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
    await send(player.page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
  await send(player.page, "POST", `/api/characters/${id}/creation/complete`);
  const asked = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  const now = Date.now();
  const cycle = await send(lead.page, "POST", `/api/troupes/${troupe.id}/cycles`, {
    name: "Quiet month",
    closes_at: new Date(now + 7 * 86400e3).toISOString(),
    grace_ends_at: new Date(now + 9 * 86400e3).toISOString(),
  });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/open`);

  // On a phone, the deadline comes before the first question (on a desktop it is beside them).
  const p = player.page;
  await p.goto(`/characters/${id}/downtime`);
  const due = p.getByText(/^Due /);
  await expect(due).toBeVisible();
  if (test.info().project.name === "phone")
    expect((await due.boundingBox())!.y).toBeLessThan((await p.getByRole("heading", { name: "Feeding" }).boundingBox())!.y);

  // The answer saves itself once typing stops, and is there after a reload.
  const saved = p.getByText(/^Saved \d/);
  await p.getByRole("button", { name: /Add an action/ }).first().click();
  const answer = p.getByLabel("Downtime action");
  await answer.fill("Watch the docks for the courier.");
  await expect(p.getByText("Not saved yet")).toBeVisible();
  await expect(saved).toBeVisible({ timeout: 10_000 });
  await p.reload();
  await expect(answer).toHaveValue("Watch the docks for the courier.");

  // A save that can't get through says so, and the writing stays.
  await p.route("**/downtime/answers", (route) => route.abort());
  const longer = "Watch the docks for the courier, then follow him to his haven.";
  await answer.fill(longer);
  await expect(p.getByText("Couldn't save:")).toBeVisible({ timeout: 10_000 });
  // Staff give another action meanwhile, and the page asks again when the player comes back to it.
  const [participant] = await send(lead.page, "GET", `/api/cycles/${cycle.id}/participants`);
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/participants/${participant.id}/adjustments`, { action_kind: "general", delta: 1, reason: "Helped at game" });
  await p.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await expect(p.getByText("+1 general: Helped at game")).toBeVisible();
  await expect(answer).toHaveValue(longer);
  await p.unroute("**/downtime/answers");
  await p.getByRole("button", { name: "try again" }).click();
  await expect(saved).toBeVisible();

  // Removing an action can be undone.
  await p.getByRole("button", { name: "Remove this action" }).click();
  await expect(answer).toHaveCount(0);
  await p.getByRole("button", { name: "Undo" }).click();
  await expect(answer).toHaveValue(longer);
  await expect(saved).toBeVisible({ timeout: 10_000 });
  await p.screenshot(shots("downtime-saved"));
  await p.reload();
  await expect(answer).toHaveValue(longer);
});

test("a character's tabs show a downtime due and new results, and on a phone both are a tap away without scrolling sideways (#360)", async ({ browser }) => {
  const custodian = await person(browser, "dtcount-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "dtcount-lead");
  const player = await person(browser, "dtcount-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "GET" | "POST" | "PUT", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data: method === "GET" ? undefined : (data ?? {}) });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Waiting Counts ${run}`, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const { id } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: "Perpetua" });
  await send(player.page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
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
    await send(player.page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
  await send(player.page, "POST", `/api/characters/${id}/creation/complete`);
  const asked = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  const now = Date.now();
  const cycle = await send(lead.page, "POST", `/api/troupes/${troupe.id}/cycles`, {
    name: "Counting month",
    closes_at: new Date(now + 7 * 86400e3).toISOString(),
    grace_ends_at: new Date(now + 9 * 86400e3).toISOString(),
  });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/open`);

  // On the Sheet, the downtime waiting shows. On a phone the tabs are in groups,
  // and Between games carries the count; its first two tabs are Downtime and Results.
  const p = player.page;
  const phone = test.info().project.name === "phone";
  const width = p.viewportSize()!.width;
  const main = p.locator("main");
  const sections = main.getByRole("navigation", { name: "Tab groups" });
  const between = main.getByRole("navigation", { name: "Between games", exact: true });
  const fits = async (link: ReturnType<Page["getByRole"]>) => {
    const box = (await link.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
  };
  await p.goto(`/characters/${id}`);
  if (phone) {
    const group = sections.getByRole("link", { name: "Between games 1 waiting" });
    await fits(group);
    await p.screenshot(shots("character-tabs-grouped"));
    await group.click();
    await expect(p).toHaveURL(new RegExp(`/characters/${id}/downtime$`));
    await fits(between.getByRole("link", { name: "Downtime 1 due" }));
    await fits(between.getByRole("link", { name: "Results", exact: true }));
    await p.screenshot(shots("character-tabs-downtime-due"));
  } else {
    await expect(main.getByRole("link", { name: "Downtime 1 due" })).toBeVisible();
  }

  // Submitted, nothing is due.
  const form = await send(p, "GET", `/api/characters/${id}/downtime`);
  const question = form.questions.find((q: { prompt: string }) => q.prompt === "Downtime action");
  await send(p, "PUT", `/api/characters/${id}/downtime/answers`, { answers: [{ question_id: question.id, slot: 1, body: "Count the ships in the harbour." }] });
  await send(p, "POST", `/api/characters/${id}/downtime/submit`);
  await p.goto(`/characters/${id}`);
  if (phone) await expect(sections.getByRole("link", { name: "Between games", exact: true })).toBeVisible();
  else await expect(main.getByRole("link", { name: "Downtime", exact: true })).toBeVisible();

  // The results are delivered: new until the player opens Results.
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/close`, { add_to_ceiling: true });
  const [response] = await send(lead.page, "GET", `/api/cycles/${cycle.id}/responses`);
  await send(lead.page, "PUT", `/api/responses/${response.id}`, { body: "Eleven ships, and one flies no flag." });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/deliver`, { partial: true });
  await p.reload();
  if (phone) await expect(sections.getByRole("link", { name: "Between games 1 waiting" })).toBeVisible();
  await characterTab(p, "Results");
  await expect(p.getByText("Eleven ships, and one flies no flag.")).toBeVisible();
  if (phone) {
    await expect(between.getByRole("link", { name: "Results", exact: true })).toBeVisible();
    await expect(sections.getByRole("link", { name: "Between games", exact: true })).toBeVisible();
  } else {
    await expect(main.getByRole("link", { name: "Results", exact: true })).toBeVisible();
  }
  await p.reload();
  await expect(p.getByText("Eleven ships, and one flies no flag.")).toBeVisible();
  await expect(main.getByRole("link", { name: /^Results \d/ })).toHaveCount(0);
});

test("feeding in a downtime: Herd given to another character, both answered, and half Blood at the next game", async ({ browser }) => {
  const custodian = await person(browser, "dtfeed-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "dtfeed-lead");
  const giver = await person(browser, "dtfeed-giver");
  const receiver = await person(browser, "dtfeed-receiver");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupeName = `Hungry Night ${run}`;
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);

  // Agnes (Toreador, Herd 2) and Bram (Brujah, no Herd), both at home in the troupe.
  const build = async (page: Page, name: string, clan: string, backgrounds: [string, number][]) => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: clan, rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds,
      disciplines: clan === "Toreador" ? [["Auspex", 2], ["Celerity", 1], ["Presence", 1]] : [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
    };
    for (const [category, list] of Object.entries(picks))
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`);
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id as string;
  };
  const agnes = await build(giver.page, "Agnes", "Toreador", [["Fame", 3], ["Herd", 2], ["Generation", 1]]);
  const bram = await build(receiver.page, "Bram", "Brujah", [["Fame", 3], ["Resources", 2], ["Generation", 1]]);

  // The lead makes a cycle, and Brujah need 2 this time.
  const now = Date.now();
  const cycle = await send(lead.page, "POST", `/api/troupes/${troupe.id}/cycles`, {
    name: "Lean month",
    closes_at: new Date(now + 7 * 86400e3).toISOString(),
    grace_ends_at: new Date(now + 9 * 86400e3).toISOString(),
  });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/open`);
  const l = lead.page;
  await l.goto(`/cycles/${cycle.id}/feeding`);
  await l.getByLabel("Feeding for Brujah").fill("2");
  await l.getByLabel("Reason for Brujah").fill("riots downtown");
  await l.getByRole("listitem").filter({ hasText: "Brujah" }).getByRole("button", { name: "Save" }).click();
  await expect(l.getByText("Needs 2: Brujah 2 (riots downtown)")).toBeVisible();

  // Agnes keeps one dot of Herd for her own feeding and gives the other to Bram.
  const a = giver.page;
  await a.goto(`/characters/${agnes}/downtime`);
  const feeding = a.locator("section").filter({ has: a.getByRole("heading", { name: "Feeding" }) });
  await expect(feeding.getByText("You need 1 feeding this cycle: Toreador 1.")).toBeVisible();
  await feeding.getByLabel("Use for my feeding").fill("1");
  await feeding.getByRole("button", { name: "Give Herd to another character" }).click();
  await expect(feeding.getByLabel("Give to…")).toHaveValue(bram);
  await expect(feeding.getByText("2 of 2 dots shared out")).toBeVisible();
  await expect(feeding.getByRole("status")).toHaveText("Feeding 0 + your Herd 1 = 1 of 1 needed ✓");
  await a.screenshot(shots("downtime-feeding"));
  await a.getByRole("button", { name: "Submit downtime" }).click();
  await expect(a.getByText("submitted", { exact: true })).toBeVisible();

  // Bram sees the gift in his tally: 1 of the 2 he needs. Nothing stops him submitting.
  const b = receiver.page;
  await b.goto(`/characters/${bram}/downtime`);
  const his = b.locator("section").filter({ has: b.getByRole("heading", { name: "Feeding" }) });
  await expect(his.getByText("You need 2 feeding this cycle: Brujah 2 (riots downtown).")).toBeVisible();
  await expect(his.getByText("Agnes gave you 1 Herd.")).toBeVisible();
  await expect(his.getByRole("status")).toHaveText("Feeding 0 + 1 from Agnes = 1 of 2 needed: you'll come to game at half Blood unless staff say otherwise.");
  await his.getByLabel("Where and how").fill("The back rooms of the Rack");
  await b.getByRole("button", { name: "Submit downtime" }).click();
  await expect(b.getByText("submitted", { exact: true })).toBeVisible();

  // The tally suggests Full for Agnes and Half for Bram; the lead answers both.
  await l.reload();
  const agnesCard = l.locator("section").filter({ has: l.getByRole("heading", { name: "Agnes" }) });
  const bramCard = l.locator("section").filter({ has: l.getByRole("heading", { name: "Bram" }) });
  await expect(agnesCard.getByText("0 feeding actions · Herd: 1 for my feeding, 1 to Bram")).toBeVisible();
  await expect(agnesCard.getByRole("radio", { name: "Full Blood next game" })).toBeChecked();
  await agnesCard.getByLabel("Flavour (optional)").fill("Your admirers keep you well fed.");
  await agnesCard.getByRole("button", { name: "Answer" }).click();
  await expect(agnesCard.getByText(/How it was worked out: needed 1 \(Toreador 1\)/)).toBeVisible();
  await expect(bramCard.getByRole("radio", { name: "Half Blood next game" })).toBeChecked();
  await bramCard.getByRole("button", { name: "Answer" }).click();
  await expect(bramCard.getByText("How it was worked out: needed 2 (Brujah 2 (riots downtown)). Feeding actions 0; Herd from Agnes 1. Total 1.")).toBeVisible();
  await l.screenshot(shots("cycle-feeding"));
  await send(l, "POST", `/api/cycles/${cycle.id}/close`, { add_to_ceiling: false });
  const delivered = await send(l, "POST", `/api/cycles/${cycle.id}/deliver`);
  expect(delivered.delivered).toBe(2);

  // Each player reads the answer, with the working folded away beneath it.
  await a.goto(`/characters/${agnes}/results`);
  await expect(a.getByText("Full Blood next game.")).toBeVisible();
  await b.goto(`/characters/${bram}/results`);
  await expect(b.getByText("Half Blood next game.")).toBeVisible();
  const working = b.getByText("Feeding actions 0; Herd from Agnes 1. Total 1.", { exact: false });
  await expect(working).toBeHidden();
  await b.getByText("How it was worked out").click();
  await expect(working).toBeVisible();

  // Bram's next game starts at half Blood, rounded up; Agnes's at full.
  await b.goto(`/play/characters/${bram}`);
  await expect(b.getByLabel("Blood: 5 of 10")).toBeVisible();
  await expect(b.getByText("Half Blood: fed short last downtime")).toBeVisible();
  await b.screenshot(shots("play-half-blood"));
  await a.goto(`/play/characters/${agnes}`);
  await expect(a.getByLabel("Blood: 10 of 10")).toBeVisible();
  await expect(a.getByText("Half Blood: fed short last downtime")).toHaveCount(0);
});
