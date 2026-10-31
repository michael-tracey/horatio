import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, backstoryOptional } from "./support";

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
  await lead.page.getByRole("button", { name: "Save" }).click();
  await expect(lead.page.getByText(`@${narrator.handle} · Narrator`)).toBeVisible();

  // The player builds a character in the creation wizard, then buys Influence with XP.
  const p = player.page;
  await p.getByLabel("Name").fill("Agnes");
  // Built for the troupe from the start, so its rules and lists apply. (The page
  // loaded before the troupe existed.)
  await p.reload();
  await p.getByLabel("Name").fill("Agnes");
  await p.getByLabel("Build for").selectOption({ label: troupeName });
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
  await p.locator("main").getByRole("link", { name: "Log", exact: true }).click();
  await expect(p.getByText("bought Influences: The Elite 1 for Agnes (1 XP).", { exact: false })).toBeVisible();

  // …and asks to make the troupe its home.
  await p.locator("main").getByRole("link", { name: "Troupes", exact: true }).click();
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
  await p.locator("main").getByRole("link", { name: "Sheet", exact: true }).click();
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
  // Ticked characters print together, in a new tab.
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
  await lead.page.getByRole("link", { name: "Customize", exact: true }).click();
  await lead.page.getByRole("link", { name: "Rules", exact: true }).click();
  await lead.page.getByLabel("Search rules").fill("Calm Heart");
  await lead.page.getByLabel(/Setting for: Brujah cannot take Calm Heart/).selectOption({ label: "Allow, for our review" });
  await expect(lead.page.getByText("Only those played differently (1)")).toBeVisible();
  await lead.page.screenshot(shots("rules"));
  // …and set its own price: Generation 1 skills at a flat 1 XP a dot, which Agnes pays.
  await lead.page.getByRole("link", { name: "Costs", exact: true }).click();
  await lead.page.getByRole("button", { name: "Change the price for All skills, Generation 1" }).click();
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
  await p.locator("main").getByRole("link", { name: "Sheet", exact: true }).click();
  await p.getByRole("button", { name: "Raise Investigation" }).click();
  // Until it is spent, the sheet shows what the rating would become.
  const investigation = p.locator("li", { has: p.getByRole("button", { name: "Raise Investigation" }) });
  await expect(investigation.getByLabel("1 dots, 2 after the changes in the cart")).toHaveText("1 → 2");
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 1 XP.")).toBeVisible();
  await expect(investigation.getByLabel("2 dots", { exact: true })).toHaveText("2");
  await p.locator("main").getByRole("link", { name: "Log", exact: true }).click();
  await expect(p.getByText("raised Agnes's Investigation from 1 to 2 (1 XP).", { exact: false })).toBeVisible();

  // The troupe lists the areas its Elite influence covers; Agnes picks one.
  await lead.page.getByRole("link", { name: "Customize", exact: true }).click();
  await lead.page.getByRole("link", { name: "Specialisations", exact: true }).click();
  await lead.page.getByRole("navigation", { name: "Backgrounds" }).getByRole("link", { name: "Influence: Elite" }).click();
  await expect(lead.page).toHaveURL(/\/specializations\/influence-elite$/);
  await lead.page.screenshot(shots("troupe-specializations"));
  const elite = lead.page.locator("section").filter({ has: lead.page.getByRole("heading", { name: "Influence: Elite", exact: true }) });
  await elite.getByRole("button", { name: "Make our own list" }).click();
  await elite.getByLabel("Influence: Elite, one per line").fill("Police\nFinance");
  await elite.getByRole("button", { name: "Save our list" }).click();
  await expect(elite.getByText("Finance, Police")).toBeVisible();
  await p.locator("main").getByRole("link", { name: "Sheet", exact: true }).click();
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
  await p.getByRole("link", { name: "Downtime", exact: true }).click();
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
  await lead.page.getByLabel("Assign to").first().selectOption({ label: "narrator" });
  await expect(lead.page.getByLabel("Assign to").first()).toHaveValue(/.+/);
  await narrator.page.getByRole("link", { name: "Troupes" }).click();
  await narrator.page.getByRole("link", { name: troupeName }).click();
  await narrator.page.getByRole("link", { name: "Downtimes", exact: true }).click();
  await narrator.page.getByRole("link", { name: "My work" }).click();
  await narrator.page.getByRole("link", { name: "November" }).click();
  await narrator.page.getByLabel("Response to Agnes").fill("The docks are crowded tonight; you feed well and unseen.");
  await narrator.page.getByRole("button", { name: "Save response" }).click();
  await expect(narrator.page.getByText("written", { exact: true })).toBeVisible();
  await narrator.page.screenshot(shots("narrator"));

  // The lead closes and delivers; the player reads the result.
  await lead.page.getByRole("link", { name: "Overview" }).click();
  await lead.page.getByRole("button", { name: "Close submissions" }).click();
  await lead.page.getByRole("button", { name: "Deliver results" }).click();
  await expect(lead.page.getByText("Delivered 1 downtime.")).toBeVisible();
  // The Delivery tab shows each participant against each channel; with no connectors, in Horatio only.
  await lead.page.getByRole("link", { name: "Delivery", exact: true }).click();
  await expect(lead.page.getByRole("columnheader", { name: "In Horatio" })).toBeVisible();
  await expect(lead.page.getByRole("row", { name: /Agnes.*sent/ })).toBeVisible();
  await lead.page.getByRole("link", { name: "Overview" }).click();
  await p.getByRole("link", { name: "Results" }).click();
  await expect(p.getByText("you feed well and unseen")).toBeVisible();
  await p.screenshot(shots("results"));

  // Results always go out in Horatio; Discord needs the server set up first.
  await lead.page.getByRole("link", { name: "Troupes" }).click();
  await lead.page.getByRole("link", { name: troupeName }).click();
  await lead.page.getByRole("link", { name: "Customize", exact: true }).click();
  await lead.page.getByRole("link", { name: "Connectors", exact: true }).click();
  await expect(lead.page.getByText("always on")).toBeVisible();
  await expect(lead.page.getByText(/Discord is not set up on this server/)).toBeVisible();
  await expect(lead.page.getByText(/Email is not set up on this server/)).toBeVisible();

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
  await p.getByRole("link", { name: "Sheet", exact: true }).click();
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
