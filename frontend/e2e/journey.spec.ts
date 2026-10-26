import { execFileSync } from "node:child_process";
import { expect, test, type Browser, type BrowserContextOptions, type Page } from "@playwright/test";

/**
 * One troupe's month, end to end: the custodian sets up a troupe, a player
 * builds a character and brings it to the troupe, the lead approves it and runs
 * a downtime cycle, a narrator answers an action, and the player reads the
 * results. Each person is a separate browser session.
 */

const run = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
const PASSWORD = "a long enough password";
const shots = (name: string) => ({ path: `test-results/screens/${test.info().project.name}-${name}.png`, fullPage: true });

async function person(browser: Browser, name: string, options: BrowserContextOptions = {}): Promise<{ page: Page; email: string; handle: string }> {
  const page = await (await browser.newContext(options)).newPage();
  const email = `${name}-${run}@example.com`;
  // Unique to the run, and within a handle's 30 characters.
  const handle = `${name.slice(0, 14)}_${run.slice(-10)}`;
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill(name);
  await page.getByLabel("Handle").fill(handle);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your characters" })).toBeVisible();
  return { page, email, handle };
}

// Playwright leaves contexts made from `browser` open after the test. Each page in
// them goes on polling the API, so by the end of a worker's run hundreds of them
// load the one server the later tests wait on. Screenshots and traces of a failure
// are taken before this, and as each context closes.
test.afterEach(async ({ browser }) => {
  await Promise.all(browser.contexts().map((context) => context.close()));
});

/** How many pages a PDF that Chromium printed has, and the first one's size in points. */
function pdfPages(pdf: Buffer): { count: number; size: string } {
  const text = pdf.toString("latin1");
  const box = text.match(/\/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]/)!;
  return { count: text.match(/\/Type \/Page\b/g)?.length ?? 0, size: `${Math.round(Number(box[1]))} × ${Math.round(Number(box[2]))}` };
}

function makeCustodian(email: string) {
  execFileSync("uv", ["run", "python", "-m", "horatio.custodian", email], { cwd: "../backend", stdio: "ignore" });
}

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


test("a troupe changes what new characters start with and their downtime actions", async ({ browser }) => {
  const custodian = await person(browser, "start-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "start-lead");
  const player = await person(browser, "start-player");
  const troupeName = `Court of Embers ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // The lead gives new characters a bigger merit budget.
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await l.getByRole("link", { name: "Customize", exact: true }).click();
  await l.getByRole("link", { name: "Rules", exact: true }).click();
  await l.getByRole("link", { name: "Starting points", exact: true }).click();
  await l.getByRole("button", { name: "Change starting Merits" }).click();
  await l.getByLabel("Points for merits").fill("9");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("The rule set's: 7 points")).toBeVisible();
  await l.screenshot(shots("starting"));
  // …and four downtime actions a cycle instead of three.
  await l.getByRole("link", { name: "Downtime actions", exact: true }).click();
  await l.getByRole("button", { name: "Change actions for Everyone" }).click();
  await l.getByLabel("Downtime actions each cycle").fill("4");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("replaced here")).toBeVisible();
  await expect(l.getByText("4 downtime actions")).toBeVisible();
  await l.screenshot(shots("actions"));

  // A character built for the troupe has that budget in the wizard.
  const p = player.page;
  await p.reload();
  await p.getByLabel("Name").fill("Mara");
  await p.getByLabel("Build for").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Create" }).click();
  await p.getByLabel("Clan").selectOption("Brujah");
  await expect(p.getByLabel("Clan")).toHaveValue("Brujah");
  for (const heading of ["Attributes", "Focuses", "Skills", "Backgrounds", "Disciplines", "Merits & flaws"]) {
    // A vampire needs Generation before leaving Backgrounds.
    if (heading === "Disciplines") await p.getByRole("button", { name: "Generation 1", exact: true }).click();
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
  }
  await expect(p.getByText("0 of 9 points")).toBeVisible();
});

test("a troupe's own merits: staff only, or taken when building for it, and marked ★ as the troupe's", async ({ browser }) => {
  const custodian = await person(browser, "hm-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "hm-lead");
  const player = await person(browser, "hm-player");
  const troupeName = `Court of Stars ${run}`;
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  const mark = `House merit of ${troupeName}`;

  // The lead makes two on the Rules tab: one only staff give, one players can take when building.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/rules/house-traits`);
  const addOne = async (name: string, points: string, availability: string, description: string) => {
    await l.getByRole("button", { name: "Add a merit or flaw" }).click();
    await l.getByLabel("Name").fill(name);
    await l.getByLabel("Points").selectOption(points);
    await l.getByLabel(availability).check();
    await l.getByLabel("Description").fill(description);
    await l.getByRole("button", { name: "Add the merit" }).click();
    await expect(l.getByRole("listitem").filter({ hasText: name })).toBeVisible();
  };
  await addOne("Favour of the Crossroads", "2", "Given by staff only", "The Prince owes you one.");
  await addOne("Child of the Stars", "1", "Available when building for the troupe", "Born under a lucky sign.");
  await expect(l.getByRole("listitem").filter({ hasText: "Favour of the Crossroads" })).toContainText(mark);
  await l.screenshot(shots("house-traits"));

  // Lune is built for the troupe through the API, and visits it so its staff see her.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const build = async (name: string, buildingFor: string | null) => {
    const { id } = await send("POST", "/api/characters", { splat: "vampire", name, building_troupe_id: buildingFor });
    await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
      disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
    };
    for (const [category, list] of Object.entries(picks))
      await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send("POST", `/api/characters/${id}/creation/complete`, {});
    await send("POST", `/api/characters/${id}/troupes`, { troupe_id: troupeId });
    return id as string;
  };
  const lune = await build("Lune", troupeId);

  // Building for the troupe, she is offered the one players can take, not the one staff give.
  await p.goto(`/characters/${lune}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Merits").fill("Favour of the");
  await expect(p.getByRole("button", { name: /^Favour of the Crossroads/ })).toHaveCount(0);
  await p.getByLabel("Search Merits").fill("Child of the");
  await expect(p.getByRole("button", { name: /^Child of the Stars/ })).toContainText(mark);
  await p.getByRole("button", { name: /^Child of the Stars/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(part("Merits and Flaws")).toContainText("Child of the Stars");
  await expect(part("Merits and Flaws")).toContainText(`★${mark}`);

  // The lead gives her the staff-only one, free, with a reason.
  await l.goto(`/characters/${lune}`);
  const house = l.locator("section").filter({ has: l.getByRole("heading", { name: "House merits and flaws", exact: true }) });
  await house.getByRole("button", { name: "Apply Favour of the Crossroads" }).click();
  await house.getByLabel("Reason").fill("Saved the Prince's ghoul");
  await house.getByRole("button", { name: "Apply Favour of the Crossroads" }).click();
  const merits = l.locator("section").filter({ has: l.getByRole("heading", { name: "Merits and Flaws", exact: true }) });
  await expect(merits).toContainText("Favour of the Crossroads");
  await expect(merits).toContainText("given by staff, free");
  await l.screenshot(shots("house-traits-applied"));
  await p.reload();
  await expect(part("Merits and Flaws")).toContainText("Favour of the Crossroads");
  await p.locator("main").getByRole("link", { name: "Log", exact: true }).click();
  await expect(p.getByText(/the house merit of .* ★ Favour of the Crossroads \(free\): Saved the Prince's ghoul/)).toBeVisible();

  // A character only visiting the troupe is offered neither, by the player's list or by staff.
  const visitor = await build("Isaure", null);
  await p.goto(`/characters/${visitor}`);
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Merits").fill("Child of the");
  await expect(p.getByRole("button", { name: /^Child of the Stars/ })).toHaveCount(0);
  await l.goto(`/characters/${visitor}`);
  await expect(l.getByRole("heading", { name: "Attributes", exact: true })).toBeVisible();
  await expect(l.getByRole("heading", { name: "House merits and flaws", exact: true })).toHaveCount(0);
});

test("a troupe's XP floor and ceiling: new characters start at the floor, and staff settle a joiner's XP", async ({ browser }) => {
  // A whole character creation, then a home troupe request.
  test.slow();
  const custodian = await person(browser, "floor-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "floor-lead");
  const player = await person(browser, "floor-player");
  const troupeName = `Court of Bones ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // The chronicle began before Horatio: the lead sets the floor and ceiling by hand, on About.
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await l.getByRole("button", { name: "Set by hand" }).click();
  await l.getByLabel("Floor", { exact: true }).fill("100");
  await l.getByLabel("Ceiling", { exact: true }).fill("120");
  await l.getByLabel("Why", { exact: true }).fill("Chronicle began in 2019");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("(30 starting + 70 set by hand)")).toBeVisible();
  await expect(l.getByText("(30 starting + 90 set by hand)")).toBeVisible();
  await l.screenshot(shots("xp-range"));

  // Players see where the troupe stands on its page.
  const p = player.page;
  await p.reload();
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: "XP floor and ceiling" })).toBeVisible();
  await expect(p.getByText("100 XP", { exact: true })).toBeVisible();

  // A character built for the troupe starts at its floor.
  await p.getByRole("link", { name: "Characters" }).click();
  await p.getByLabel("Name").fill("Mara");
  await p.getByLabel("Build for").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Create" }).click();
  await p.getByLabel("Clan").selectOption("Brujah");
  await expect(p.getByLabel("Clan")).toHaveValue("Brujah");
  await p.getByLabel("Sect").selectOption("Camarilla");
  const next = async (heading: string) => {
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
  };
  const tap = async (...dots: string[]) => {
    for (const dot of dots) await p.getByRole("button", { name: dot, exact: true }).click();
  };
  await next("Attributes");
  await tap("Physical 7", "Social 5", "Mental 3");
  await next("Focuses");
  await tap("Strength 1", "Wits 1", "Charisma 1");
  await next("Skills");
  await tap("Brawl 4", "Dodge 3", "Athletics 3", "Awareness 2", "Empathy 2", "Firearms 2");
  await tap("Investigation 1", "Leadership 1", "Medicine 1", "Melee 1");
  await next("Backgrounds");
  await tap("Fame 3", "Herd 2", "Generation 1");
  await next("Disciplines");
  await tap("Celerity 2", "Potence 1", "Presence 1");
  await next("Merits & flaws");
  await next("Review");
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  await p.locator("main").getByRole("link", { name: "Experience", exact: true }).click();
  await expect(p.getByText(`Starting experience: ${troupeName}'s XP floor`)).toBeVisible();

  // Mara was played elsewhere first: her player adds that XP themselves.
  await p.getByLabel("XP", { exact: true }).fill("30");
  await p.getByLabel("Why", { exact: true }).fill("Played at another troupe");
  await p.getByRole("button", { name: "Add", exact: true }).click();
  await expect(p.getByText("self-entered", { exact: true })).toBeVisible();

  // Asking to make the troupe her home, she sees she is above its ceiling.
  await p.locator("main").getByRole("link", { name: "Troupes", exact: true }).click();
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: troupeName });
  await expect(p.getByText("That is 10 XP above the ceiling.", { exact: false })).toBeVisible();
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(/Waiting for .* storytellers/)).toBeVisible();

  // The lead sees the self-entered XP apart, and what is above the ceiling, and removes it.
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: /Approvals/ }).click();
  await expect(l.getByLabel("Self-entered XP: 30")).toBeVisible();
  await l.getByLabel("Above the ceiling by 10 XP").selectOption({ label: "Remove the 10 XP above the ceiling" });
  await expect(l.getByText("After joining it will have been given 120 XP.", { exact: false })).toBeVisible();
  await l.screenshot(shots("xp-approval"));
  await l.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();

  // Taking it away is its own entry in Mara's XP history.
  await p.locator("main").getByRole("link", { name: "Experience", exact: true }).click();
  await expect(p.getByText(`XP above ${troupeName}'s ceiling of 120`)).toBeVisible();
  await expect(p.getByText("above a ceiling", { exact: true })).toBeVisible();
});

test("Generation changes in the cart until a home troupe accepts the character, repricing earlier buys", async ({ browser }) => {
  const custodian = await person(browser, "gen-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "gen-lead");
  const player = await person(browser, "gen-player");
  const troupeName = `Court of the Unaccepted ${run}`;
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;

  // Ottoline, a Neonate (Generation 1), finishes creation and buys Brawl and Herd at a Neonate's prices: 5 and 3 XP.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Ottoline" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const build: Record<string, [string, number][]> = {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, picks] of Object.entries(build))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});
  await send("PUT", `/api/characters/${id}/traits`, { category: "skills", name: "Brawl", rating: 5 });
  await send("PUT", `/api/characters/${id}/traits`, { category: "backgrounds", name: "Herd", rating: 3 });
  await p.goto(`/characters/${id}`);
  const cart = p.getByRole("list", { name: "Changes in the cart" });

  // No troupe has accepted her yet, so Generation still goes up in the cart: 4 XP, and the earlier buys at Generation 2's prices.
  await p.getByRole("button", { name: "Raise Generation" }).click();
  const line = cart.getByRole("listitem").filter({ hasText: "Generation 1 → 2" });
  await expect(line).toContainText("Generation 1 → 2 · 12 XP");
  await expect(line).toContainText("Earlier buys repriced at the new Generation, 8 XP in all: Brawl 4 → 5 (5 XP), Herd 2 → 3 (3 XP).");
  await p.screenshot(shots("generation-repriced"));
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 12 XP.")).toBeVisible();
  await p.locator("main").getByRole("link", { name: "Experience", exact: true }).click();
  await expect(p.getByText("Generation 1 → 2: Brawl 4 → 5 repriced")).toBeVisible();
  await expect(p.getByText("Generation 1 → 2: Herd 2 → 3 repriced")).toBeVisible();

  // Down again refunds the dot and reprices back; the creation pick stays.
  await p.goto(`/characters/${id}`);
  await p.getByRole("button", { name: "Lower Generation" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Generation 2 → 1" })).toContainText("8 XP back in all");
  await expect(p.getByRole("button", { name: "Lower Generation" })).toBeDisabled();
  await p.getByRole("button", { name: "Clear" }).click();

  // The lead sees the Generation being accepted, and that accepting locks it.
  const asked = await send("POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  expect(asked.id).toBeTruthy();
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/approvals`);
  const card = l.locator("section").filter({ hasText: "Ottoline" });
  await expect(card).toContainText("Accepting at Generation 2.");
  await expect(card).toContainText("Accepting locks it");
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();

  // Once accepted, Generation is fixed.
  await p.reload();
  await p.getByRole("button", { name: "Raise Generation" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Generation 2 → 3" })).toContainText(
    "Generation can't change once a home troupe has accepted the character.",
  );
  await expect(p.getByRole("button", { name: "Spend XP" })).toBeDisabled();
});

test("a character in no troupe can be deleted from the vault", async ({ browser }) => {
  const { page } = await person(browser, "deleter");
  await page.getByLabel("Name").fill("Short-lived");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  // Delete waits behind the ⋯ menu beside Play, and asks first.
  await page.getByRole("button", { name: "More for Short-lived" }).click();
  await page.getByRole("menuitem", { name: "Delete…" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete Short-lived for good" }).click();

  await expect(page.getByRole("heading", { name: "Your characters" })).toBeVisible();
  await expect(page.getByText("No characters yet.")).toBeVisible();
});

test("storytellers build an NPC quickly and give it a title", async ({ browser }) => {
  const custodian = await person(browser, "npc-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "npc-lead");
  const troupeName = `Court of Smoke ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  const created = custodian.page.waitForResponse((r) => r.url().endsWith("/api/troupes") && r.request().method() === "POST");
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  const response = await created;
  expect(response.status(), await response.text()).toBe(201);
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await p.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await p.locator("main").getByRole("link", { name: "NPCs", exact: true }).click();
  await expect(p.getByRole("heading", { name: "New NPC" })).toBeVisible();
  await p.getByLabel("Name").fill("Prince Vasquez");
  await p.getByRole("button", { name: "Quick build" }).click();
  await expect(p.getByRole("heading", { name: "Prince Vasquez" })).toBeVisible();

  await p.getByLabel("Clan", { exact: true }).selectOption("Ventrue");
  await expect(p.getByLabel("Clan", { exact: true })).toHaveValue("Ventrue");
  await p.getByRole("button", { name: "Social 7", exact: true }).click(); // attributes: 3 a dot
  await expect(p.getByText("21 XP")).toBeVisible();
  // Each attribute's focus is chosen beside it, one of three; choosing again swaps it.
  await expect(p.getByRole("heading", { name: "Focuses" })).toHaveCount(0);
  await p.getByLabel("Social focus").selectOption("Charisma");
  await expect(p.getByLabel("Social focus")).toHaveValue("Charisma");
  await p.getByLabel("Social focus").selectOption("Manipulation");
  await expect(p.getByLabel("Social focus")).toHaveValue("Manipulation");
  await expect(p.getByText("21 XP")).toBeVisible(); // focuses are free
  await p.getByRole("button", { name: "Leadership 3", exact: true }).click(); // 1 + 2 + 3
  await expect(p.getByText("27 XP")).toBeVisible();
  // Morality is one path at one rating: moving to a Path keeps the rating, free.
  await expect(p.getByLabel("Morality", { exact: true })).toHaveValue("Humanity");
  await p.getByRole("button", { name: "Humanity 4", exact: true }).click();
  await expect(p.getByRole("button", { name: "Humanity 4", exact: true })).toHaveAttribute("aria-pressed", "true");
  await p.getByLabel("Morality", { exact: true }).selectOption("Caine");
  await expect(p.getByRole("button", { name: "Caine 4", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(p.getByRole("button", { name: /^Humanity \d+$/ })).toHaveCount(0);
  await expect(p.getByText("27 XP")).toBeVisible();
  await p.screenshot(shots("npc"));

  // Its badge, from the Build tab: the same dialog as a player character's, then printing.
  await p.getByRole("button", { name: "Badge", exact: true }).click();
  await expect(p.getByRole("dialog").getByText("Path of Caine")).toBeVisible();
  const npcBadgeTab = p.context().waitForEvent("page");
  await p.getByRole("dialog").getByRole("button", { name: "Print badge" }).click();
  const npcBadge = await npcBadgeTab;
  await expect(npcBadge.getByRole("article", { name: "Badge for Prince Vasquez" }).getByText("Ventrue · Neonate")).toBeVisible();
  await npcBadge.close();
  await p.getByRole("dialog").getByRole("button", { name: "Close" }).click();

  // Titles are given on the troupe's Characters tab.
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await p.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await p.getByRole("button", { name: "Give Prince Vasquez a title" }).click();
  await p.getByRole("dialog").getByLabel("Title").fill("Prince");
  await p.screenshot(shots("give-title"));
  await p.getByRole("dialog").getByLabel("Title").press("Enter");
  await expect(p.getByRole("button", { name: "Take the title Prince from Prince Vasquez" })).toBeVisible();
  await p.screenshot(shots("roster-titles"));
  await p.getByRole("link", { name: "Troupe", exact: true }).click();
  await p.locator("main").getByRole("link", { name: "Log", exact: true }).click();
  await expect(p.getByText("npc-lead gave Prince Vasquez the title Prince.")).toBeVisible();

  // The NPC list: badges for those ticked or for every NPC, and each one's Play View.
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const another = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers: { "X-Horatio": "1" }, data: { name: "Sheriff Ilse", wizard: false } });
  expect(another.status(), await another.text()).toBe(201);
  await p.goto(`/troupes/${troupeId}/npcs`);
  await p.getByLabel("Select Prince Vasquez").check();
  let badgesTab = p.context().waitForEvent("page");
  await p.getByRole("button", { name: "Badges for selected (1)" }).click();
  let badges = await badgesTab;
  await expect(badges.getByRole("article")).toHaveCount(1);
  await expect(badges.getByRole("article", { name: "Badge for Prince Vasquez" }).getByText("Prince", { exact: true })).toBeVisible();
  await badges.close();
  badgesTab = p.context().waitForEvent("page");
  await p.getByRole("button", { name: "Badges for all NPCs" }).click();
  badges = await badgesTab;
  await expect(badges.getByRole("article")).toHaveCount(2);
  await expect(badges.getByRole("article", { name: "Badge for Sheriff Ilse" })).toBeVisible();
  await badges.close();
  await p.screenshot(shots("npcs"));
  await p.getByRole("link", { name: "Play Sheriff Ilse" }).click();
  await expect(p.getByRole("heading", { name: "Sheriff Ilse" })).toBeVisible();
  await expect(p.getByRole("tab", { name: "Tracker" })).toBeVisible();
});

test("storytellers make NPCs of other kinds, sheeted or Stock, and filter the list by kind and form", async ({ browser }) => {
  const custodian = await person(browser, "kinds-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "kinds-lead");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Antlers ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;

  const p = lead.page;
  await p.goto(`/troupes/${troupeId}/npcs`);
  await expect(p.getByRole("heading", { name: "New NPC" })).toBeVisible();
  // A Stock werewolf: the kind's resource and pages show as it is picked.
  await p.getByLabel("Name").fill("Bites-the-Hand");
  await p.getByLabel("Kind", { exact: true }).selectOption("werewolf");
  await expect(p.getByText("Supernatural · Rage 10, up to 3 a turn, regains 1 every five turns · pp. 494–495")).toBeVisible();
  await p.getByRole("radio", { name: "Stock" }).click();
  await p.getByLabel("Rating").fill("3");
  await p.getByRole("button", { name: "Make Stock NPC" }).click();
  const wolf = p.getByRole("listitem", { name: "Bites-the-Hand" });
  await expect(wolf.getByText("Werewolf")).toBeVisible();
  await expect(wolf.getByText("Stock", { exact: true })).toBeVisible();
  await expect(wolf.getByText("Rating 3")).toBeVisible();
  // A Stock NPC has no sheet yet to play from.
  await expect(p.getByRole("link", { name: "Play Bites-the-Hand" })).toHaveCount(0);

  // A sheeted mage goes to its quick build, on the Vampire sheet.
  await p.getByLabel("Name").fill("Sarah Juniper");
  await p.getByLabel("Kind", { exact: true }).selectOption("mage");
  await p.getByRole("radio", { name: "Sheeted" }).click();
  await p.getByRole("button", { name: "Quick build" }).click();
  await expect(p.getByRole("heading", { name: "Sarah Juniper" })).toBeVisible();

  await p.goto(`/troupes/${troupeId}/npcs`);
  const mage = p.getByRole("listitem", { name: "Sarah Juniper" });
  await expect(mage.getByText("Mage")).toBeVisible();
  await expect(mage.getByText("Sheeted")).toBeVisible();
  await expect(p.getByRole("link", { name: "Play Sarah Juniper" })).toBeVisible();
  await p.screenshot(shots("npc-kinds"));

  // The filter: by form, then by kind.
  await p.getByLabel("Show form").selectOption("stock");
  await expect(wolf).toBeVisible();
  await expect(mage).toHaveCount(0);
  await p.getByLabel("Show form").selectOption("");
  await p.getByLabel("Show kind").selectOption("mage");
  await expect(mage).toBeVisible();
  await expect(wolf).toHaveCount(0);
  await p.getByLabel("Show form").selectOption("stock");
  await expect(p.getByText("No NPCs of that kind.")).toBeVisible();
});

test("storytellers build a Stock NPC from the NPCs tab and see the book's stat block", async ({ browser }) => {
  const custodian = await person(browser, "stockb-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "stockb-lead");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Moss ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;

  const p = lead.page;
  await p.goto(`/troupes/${troupeId}/npcs`);
  await p.getByLabel("Name").fill("Gnashes-the-Moon");
  await p.getByLabel("Kind", { exact: true }).selectOption("werewolf");
  await p.getByRole("radio", { name: "Stock" }).click();
  await p.getByLabel("Rating").fill("3");
  await p.getByRole("button", { name: "Make Stock NPC" }).click();
  await p.getByRole("listitem", { name: "Gnashes-the-Moon" }).getByRole("link", { name: "Gnashes-the-Moon" }).click();
  await expect(p.getByRole("heading", { name: "Gnashes-the-Moon" })).toBeVisible();

  const add = async (choice: string) => {
    await p.getByLabel("Add a specialization").selectOption(choice);
    await p.getByRole("button", { name: "Add", exact: true }).click();
  };
  await add("skill:Brawl");
  await add("power:Celerity");
  const block = p.getByRole("list", { name: "Stat block" });
  await expect(block.getByText("Test pool 6 in most challenges")).toBeVisible();
  await expect(block.getByText("Brawl 11")).toBeVisible();
  await expect(block.getByText("Celerity up to 3")).toBeVisible();
  await expect(block.getByText("Rage 10, up to 3 a turn")).toBeVisible();
  await expect(block.getByText("6 health")).toBeVisible();
  await expect(block.getByText("No Willpower: no retests unless it overbids")).toBeVisible();
  await expect(p.getByRole("heading", { name: "Werewolf rules card" })).toBeVisible();
  await p.screenshot(shots("stock-npc-builder"));

  // The rating holds the count; a discipline off the werewolf's list is refused.
  await add("power:Dominate");
  await expect(p.getByText("Werewolf Stock NPCs cannot specialize in Dominate.")).toBeVisible();
  await expect(p.getByRole("listitem", { name: "Dominate" })).toHaveCount(0);
  await add("skill:Stealth");
  await expect(p.getByRole("heading", { name: "Specializations (3 of 3)" })).toBeVisible();
  await add("skill:Melee");
  await expect(p.getByText("as many specializations as its rating")).toBeVisible();
  await expect(p.getByRole("listitem", { name: "Melee" })).toHaveCount(0);
});

test("storytellers give an NPC powers, and one out of order is marked until it is in order", async ({ browser }) => {
  const custodian = await person(browser, "powers-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "powers-lead");
  const troupeName = `Court of Kindling ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  const created = custodian.page.waitForResponse((r) => r.url().endsWith("/api/troupes") && r.request().method() === "POST");
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  const troupeId = (await (await created).json()).id as string;
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  const p = lead.page;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Matriarch Odile", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  for (const [category, name, rating] of [
    ["clan", "Toreador", null],
    ["backgrounds", "Generation", 2],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category, name, rating, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
  }

  // Each tap saves and works the marks out again, which takes a while under load.
  const slowly = expect.configure({ timeout: 20_000 });
  await p.goto(`/characters/${npc}`);
  await slowly(p.getByRole("heading", { name: "Techniques", exact: true })).toBeVisible();

  // A technique is found by search and added at once; its disciplines are missing, so it is marked.
  await p.getByLabel("Search Techniques").fill("Da Shealladh");
  await p.getByRole("checkbox", { name: "An Da Shealladh" }).click();
  await slowly(p.getByRole("checkbox", { name: "An Da Shealladh" })).toBeChecked();
  await p.getByLabel("Search Techniques").fill("");
  await slowly(p.getByRole("checkbox", { name: "An Da Shealladh" })).toBeChecked();
  await slowly(p.getByText("Marked: An Da Shealladh needs Dementation 3 and Auspex 2.")).toBeVisible();

  // Adding the disciplines clears the mark.
  await p.getByLabel("Search Disciplines").fill("Dementation");
  await p.getByRole("button", { name: "Dementation 3", exact: true }).click();
  await slowly(p.getByRole("button", { name: "Dementation 3", exact: true })).toHaveAttribute("aria-pressed", "true");
  await p.getByLabel("Search Disciplines").fill("Auspex");
  await p.getByRole("button", { name: "Auspex 2", exact: true }).click();
  await slowly(p.getByRole("button", { name: "Auspex 2", exact: true })).toHaveAttribute("aria-pressed", "true");
  await slowly(p.getByText("Marked: An Da Shealladh")).toHaveCount(0);
  await slowly(p.getByRole("checkbox", { name: "An Da Shealladh" })).toBeChecked();

  // An elder power, a ritual (shown with its level) and an extra in-clan discipline.
  await p.getByLabel("Search Elder & luminary powers").fill("Crimson Fury");
  await p.getByRole("checkbox", { name: "Animalism: Crimson Fury" }).click();
  await slowly(p.getByRole("checkbox", { name: "Animalism: Crimson Fury" })).toBeChecked();
  await slowly(p.getByText("Marked: A Neonate's or Ancilla's blood is too thin for elder powers.")).toBeVisible();

  await p.getByLabel("Search Rituals").fill("Abyssal Ichor");
  await p.getByRole("checkbox", { name: "Abyssal: Abyssal Ichor" }).click();
  await slowly(p.getByRole("checkbox", { name: "Abyssal: Abyssal Ichor" })).toBeChecked();

  await p.getByLabel("Search Extra in-clan disciplines").fill("Fortitude");
  await p.getByRole("checkbox", { name: "Fortitude", exact: true }).click();
  await slowly(p.getByRole("checkbox", { name: "Fortitude", exact: true })).toBeChecked();

  // They are on the sheet, and stay after a reload; one tap takes a power off.
  await p.reload();
  for (const name of ["An Da Shealladh", "Animalism: Crimson Fury", "Abyssal: Abyssal Ichor", "Fortitude"]) {
    await slowly(p.getByRole("checkbox", { name, exact: true })).toBeChecked();
  }
  await p.getByRole("checkbox", { name: "An Da Shealladh" }).click();
  await slowly(p.getByRole("checkbox", { name: "An Da Shealladh" })).toHaveCount(0);
});

test("storytellers log influence for PCs, NPCs and names only, and a player reads their character's", async ({ browser }) => {
  // A whole character creation, then a home troupe request.
  test.slow();
  const custodian = await person(browser, "infl-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "infl-lead");
  const player = await person(browser, "infl-player");
  const troupeName = `Court of Ledgers ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // The player builds Corvin for the troupe, with Elite 3, and asks to make it home.
  const p = player.page;
  await p.reload();
  await p.getByLabel("Name").fill("Corvin");
  await p.getByLabel("Build for").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const corvin = new URL(p.url()).pathname.split("/")[2]!;
  await p.getByLabel("Clan").selectOption("Brujah");
  await p.getByLabel("Sect").selectOption("Camarilla");
  const next = async (heading: string) => {
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
  };
  const tap = async (...dots: string[]) => {
    for (const dot of dots) await p.getByRole("button", { name: dot, exact: true }).click();
  };
  await next("Attributes");
  await tap("Physical 7", "Social 5", "Mental 3");
  await next("Focuses");
  await tap("Strength 1", "Wits 1", "Charisma 1");
  await next("Skills");
  await tap("Brawl 4", "Dodge 3", "Athletics 3", "Awareness 2", "Empathy 2", "Firearms 2");
  await tap("Investigation 1", "Leadership 1", "Medicine 1", "Melee 1");
  await next("Backgrounds");
  await tap("Influences: The Elite 3", "Herd 2", "Generation 1");
  await next("Disciplines");
  await tap("Celerity 2", "Potence 1", "Presence 1");
  await next("Merits & flaws");
  await next("Review");
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  await p.locator("main").getByRole("link", { name: "Troupes", exact: true }).click();
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(/Waiting for .* storytellers/)).toBeVisible();

  // The lead accepts Corvin, keeps an NPC, and opens a cycle.
  const l = lead.page;
  await l.reload();
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;
  await l.goto(`/troupes/${troupeId}/approvals`);
  await l.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();
  const made = await l.request.post(`/api/troupes/${troupeId}/npcs`, { headers: { "X-Horatio": "1" }, data: { name: "Prince Vasquez", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  await l.goto(`/troupes/${troupeId}/downtimes`);
  await expect(l.getByRole("heading", { name: "New cycle" })).toBeVisible();
  await l.getByLabel("Name").fill("December");
  await l.getByRole("button", { name: "Create draft" }).click();
  await l.getByRole("link", { name: "December" }).click();
  await l.getByRole("button", { name: "Open for submissions" }).click();
  await expect(l.getByText("0 of 1 submitted")).toBeVisible();

  // Beside a submission on the cycle page, the tool opens with the character and cycle filled in.
  await l.getByRole("link", { name: "Participants" }).click();
  await l.getByRole("button", { name: "Log influence for Corvin" }).click();
  let form = l.getByRole("dialog").getByRole("form", { name: "Log influence" });
  await expect(form.getByLabel("Who")).toHaveValue("Corvin");
  await expect(form.getByLabel("Applies to this downtime")).toHaveValue(/.+/);
  await form.getByRole("button", { name: "Cancel" }).click();
  await expect(l.getByRole("dialog")).toBeHidden();

  // From Corvin's page: four times over his Elite 3 for December warns, and logs all the same.
  await l.goto(`/characters/${corvin}/influence`);
  await l.getByRole("button", { name: "Log influence for Corvin" }).click();
  form = l.getByRole("dialog").getByRole("form", { name: "Log influence" });
  await expect(form.getByLabel("Who")).toHaveValue("Corvin");
  await form.getByLabel("Action").selectOption({ label: "4: Smooth Over" });
  await form.getByLabel("Applies to this downtime").selectOption({ label: "December" });
  await form.getByLabel("Times taken").fill("4");
  await expect(form.getByText("Corvin has 3 Elite actions in December, and this makes 4 logged. You can still log it.")).toBeVisible();
  await form.getByLabel("Purpose").fill("To bury the inspector's report");
  await l.screenshot(shots("log-influence"));
  await form.getByRole("button", { name: "Log it", exact: true }).click();
  await expect(l.getByRole("dialog")).toBeHidden();
  const e1 = l.getByRole("listitem", { name: "Entry E1" });
  await expect(e1.getByText("To bury the inspector's report")).toBeVisible();
  await expect(e1.getByText("taken 4 times")).toBeVisible();
  await expect(e1.getByRole("link", { name: "Logged by staff, for December" })).toBeVisible();

  // On the log page, an NPC's whole month with Add another, dated by the cycle, then a name only.
  await l.goto(`/troupes/${troupeId}/influence`);
  await l.getByRole("button", { name: "Log influence" }).click();
  form = l.getByRole("form", { name: "Log influence" });
  await form.getByLabel("Who").fill("vasq");
  await form.getByRole("option", { name: /Prince Vasquez/ }).click();
  await form.getByLabel("Or date it by").selectOption({ label: "December" });
  await form.getByLabel("Specialisation").selectOption("Finance");
  await form.getByLabel("Action").selectOption({ label: "2: Gossip and Insider Trading" });
  await form.getByLabel("Purpose").fill("To hear who is buying the docks");
  await form.getByRole("button", { name: "Add another" }).click();
  await expect(form.getByText("Logged E2.")).toBeVisible();
  // The date, cycle and who stay; the rest starts again.
  await expect(form.getByLabel("Who")).toHaveValue("Prince Vasquez");
  await expect(form.getByLabel("Applies to this downtime")).toHaveValue(/.+/);
  await expect(form.getByLabel("Purpose")).toHaveValue("");
  await expect(form.getByLabel("Action")).toHaveValue("");
  await form.getByLabel("Action").selectOption({ label: "5: No Party Crashers" });
  await form.getByLabel("Purpose").fill("To keep the Anarchs out of the gala");
  await form.getByRole("button", { name: "Add another" }).click();
  await expect(form.getByText("Logged E3.")).toBeVisible();
  await form.getByLabel("Who").fill("REDACTED");
  await form.getByRole("option", { name: /^REDACTED/ }).click();
  await form.getByLabel("Type").selectOption({ label: "Underworld" });
  await form.getByLabel("Action").selectOption({ label: "5: Lockdown" });
  await form.getByRole("button", { name: "Log it", exact: true }).click();
  await expect(l.getByRole("listitem", { name: "Entry UW1" }).getByText("REDACTED")).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E3" }).getByText("By hand, for December")).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E3" }).getByText(/logged by infl-lead/)).toBeVisible();

  // The NPC's own page has its history, for staff, and the tool with it filled in.
  await l.goto(`/characters/${npc}/influence`);
  await expect(l.getByRole("listitem", { name: "Entry E3" })).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E2" })).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E1" })).toHaveCount(0);
  await expect(l.getByText("Elite: 2 spent: 2 logged by staff.")).toBeVisible();
  await l.getByRole("button", { name: "Log influence for Prince Vasquez" }).click();
  await expect(l.getByRole("dialog").getByLabel("Who")).toHaveValue("Prince Vasquez");
  await l.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();

  // The player sees Corvin's own action, and no one else's, nor the tool.
  await p.goto(`/characters/${corvin}`);
  await p.locator("main").getByRole("link", { name: "Influence", exact: true }).click();
  const own = p.getByRole("listitem", { name: "Entry E1" });
  await expect(own.getByText("Elite · 4: Smooth Over")).toBeVisible();
  await expect(own.getByText("To bury the inspector's report")).toBeVisible();
  await expect(p.getByRole("listitem", { name: /Entry (E2|E3|UW1)/ })).toHaveCount(0);
  await expect(p.getByText("Elite: 4 of 3 spent: 4 logged by staff.")).toBeVisible();
  await expect(p.getByRole("button", { name: /Log influence/ })).toHaveCount(0);
  await p.getByLabel("Findable now (last 90 days)").check();
  await expect(own).toBeVisible();
  await p.getByLabel("Type").selectOption({ label: "Underworld" });
  await expect(p.getByText("No influence actions match these filters.")).toBeVisible();
  await p.screenshot(shots("influence-history"));
});

test("a Caitiff chooses their in-clan disciplines while creating", async ({ browser }) => {
  const { page } = await person(browser, "caitiff");
  await page.getByLabel("Name").fill("Nobody's Child");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  await page.getByLabel("Clan").selectOption("Caitiff");
  for (const name of ["Auspex", "Celerity", "Potence"]) {
    await page.getByRole("checkbox", { name }).click();
    await expect(page.getByRole("checkbox", { name })).toBeChecked();
  }
  await expect(page.getByText("In-clan disciplines (3 of 3)")).toBeVisible();
  // Uncommon disciplines are not offered without a merit that opens them.
  await expect(page.getByRole("checkbox", { name: "Protean" })).toHaveCount(0);
  // With three chosen, another is still offered: tapping it asks which to swap out.
  await page.getByRole("checkbox", { name: "Dominate" }).click();
  await page.getByRole("group", { name: "Make room for Dominate" }).getByRole("button", { name: "Swap Auspex for Dominate" }).click();
  await expect(page.getByRole("checkbox", { name: "Dominate" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Auspex" })).not.toBeChecked();
  await expect(page.getByText("In-clan disciplines (3 of 3)")).toBeVisible();
});

/** A vampire in character creation built through the API: its clan, the in-clan
 * disciplines it chooses, and the creation picks of `build`. */
async function creatingVampire(p: Page, name: string, clan: string, inClan: string[], build: Record<string, [string, number][]> = {}) {
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: clan, rating: null });
  for (const discipline of inClan) await send("PUT", `/api/characters/${id}/traits`, { category: "extra_in_clan_disciplines", name: discipline, rating: 1 });
  for (const [category, picks] of Object.entries(build))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([trait, rating]) => ({ name: trait, rating })) });
  return id as string;
}

test("a Caitiff takes Vestiges of Greatness on Merits, swaps Celerity for Dementation on Concept, and is shown the starting dots to move", async ({ browser }) => {
  const { page: p } = await person(browser, "vestiges-late");
  const id = await creatingVampire(p, "Patchwork", "Caitiff", ["Auspex", "Celerity", "Potence"], {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Auspex", 1], ["Potence", 1]],
  });
  await p.goto(`/characters/${id}/create/merits`);
  await p.getByLabel("Search Merits").fill("Vestiges");
  await p.getByRole("checkbox", { name: /^Vestiges of Greatness/ }).check();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });

  // Review says what the merit opened on Concept, and links there.
  const settle = p.getByRole("region", { name: "Still to settle" });
  await expect(settle).toContainText("Vestiges of Greatness: choose one of your in-clan disciplines from Dementation");
  await settle.getByRole("link", { name: "Go to Concept" }).click();
  await expect(p.getByText("Two from the common ones and one from the uncommon ones (Vestiges of Greatness).")).toBeVisible();
  await expect(p.getByRole("group", { name: "Changed by other steps" })).toContainText("Vestiges of Greatness: choose one");

  // Three are held, but the uncommon ones are open, not greyed out: tapping one offers a swap.
  await p.getByRole("checkbox", { name: "Dementation" }).click();
  await p.getByRole("group", { name: "Make room for Dementation" }).getByRole("button", { name: "Swap Celerity for Dementation" }).click();
  await expect(p.getByRole("checkbox", { name: "Dementation" })).toBeChecked();
  await expect(p.getByRole("checkbox", { name: "Celerity" })).not.toBeChecked();
  await expect(p.getByText("Vestiges of Greatness: choose one")).toHaveCount(0);

  // The starting dots on Celerity are kept, not dropped: Concept and the stepper say they need moving.
  await expect(p.getByText("Your starting dots in Celerity need moving: it is no longer in-clan.")).toBeVisible();
  await expect(p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Disciplines \(needs a look\)/ })).toBeVisible();
  await p.getByRole("link", { name: "Go to Disciplines" }).click();
  await expect(p.getByRole("heading", { name: "Disciplines", exact: true })).toBeVisible();
  await expect(p.getByText("Your starting dots in Celerity need moving: it is no longer in-clan. Clear it and place it on another.")).toBeVisible();
  await expect(p.getByRole("button", { name: "Celerity 2" })).toHaveAttribute("aria-pressed", "true");
  await p.getByRole("button", { name: "Clear Celerity" }).click();
  await p.getByRole("button", { name: "Dementation 2" }).click();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Merits & flaws", exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(p.getByRole("navigation", { name: "Creation steps" }).getByText("(needs a look)")).toHaveCount(0);
  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Review/ }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible();
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
});

test("a Caitiff takes Vestiges of Greatness from Concept, and a second uncommon discipline is refused", async ({ browser }) => {
  const { page: p } = await person(browser, "vestiges-early");
  const id = await creatingVampire(p, "Threadbare", "Caitiff", ["Auspex", "Celerity", "Potence"]);
  await p.goto(`/characters/${id}/create/concept`);
  const fromMerits = p.getByRole("region", { name: "From merits" });
  const vestiges = fromMerits.getByRole("switch", { name: /^Vestiges of Greatness/ });
  // Each switch waits for the server, so it is tapped, then found on.
  await vestiges.click();
  await expect(vestiges).toBeChecked();
  await expect(fromMerits.getByText("3 of 7 points")).toBeVisible();
  await expect(p.getByText("Two from the common ones and one from the uncommon ones (Vestiges of Greatness).")).toBeVisible();
  await p.getByRole("checkbox", { name: "Dementation" }).click();
  await p.getByRole("group", { name: "Make room for Dementation" }).getByRole("button", { name: "Swap Potence for Dementation" }).click();
  await expect(p.getByRole("checkbox", { name: "Dementation" })).toBeChecked();

  // A second from the uncommon list is refused: the only swap offered is for the first.
  await p.getByRole("checkbox", { name: "Protean" }).click();
  const room = p.getByRole("group", { name: "Make room for Protean" });
  await expect(room).toContainText("Vestiges of Greatness gives one in-clan discipline from the uncommon list, not more.");
  await expect(room.getByRole("button", { name: /^Swap / })).toHaveText(["Swap Dementation for Protean"]);
  await room.getByRole("button", { name: "Cancel" }).click();

  // The Merits step shows the merit as taken, from the same points. (The stepper holds
  // the way there until Backgrounds has Generation.)
  await p.goto(`/characters/${id}/create/merits`);
  await expect(p.getByRole("checkbox", { name: /^Vestiges of Greatness/ })).toBeChecked();
  await expect(p.getByText("3 of 7 points")).toBeVisible();
});

test("a Caitiff chooses three common disciplines on Concept, takes Vestiges of Greatness, swaps one for Protean and finishes", async ({ browser }) => {
  const { page: p } = await person(browser, "vestiges-swap");
  const id = await creatingVampire(p, "Odd Lot", "Caitiff", [], {
    attributes: [["Mental", 7], ["Physical", 5], ["Social", 3]],
    focus_physicals: [["Dexterity", 1]],
    focus_mentals: [["Perception", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Drive", 4], ["Dodge", 3], ["Firearms", 3], ["Brawl", 2], ["Melee", 2], ["Survival", 2], ["Animal Ken", 1], ["Athletics", 1], ["Security", 1], ["Stealth", 1]],
    backgrounds: [["Contacts", 3], ["Fame", 2], ["Generation", 1]],
  });
  await p.goto(`/characters/${id}/create/concept`);
  for (const name of ["Celerity", "Fortitude", "Obfuscate"]) {
    await p.getByRole("checkbox", { name }).click();
    await expect(p.getByRole("checkbox", { name })).toBeChecked();
  }
  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Disciplines/ }).click();
  await p.getByRole("button", { name: "Celerity 2" }).click();
  await p.getByRole("button", { name: "Fortitude 1" }).click();
  await p.getByRole("button", { name: "Obfuscate 1" }).click();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Merits & flaws", exact: true })).toBeVisible({ timeout: 15_000 });
  await p.getByLabel("Search Merits").fill("Vestiges");
  await p.getByRole("checkbox", { name: /^Vestiges of Greatness/ }).check();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });

  // Everything is placed, but Review says the merit still waits on a choice, and where.
  const settle = p.getByRole("region", { name: "Still to settle" });
  await expect(settle).toContainText("Vestiges of Greatness: choose one of your in-clan disciplines from Dementation");
  await expect(p.getByText("Everything is placed. Settle what is listed above to finish.")).toBeVisible();
  await settle.getByRole("link", { name: "Go to Concept" }).click();

  // The uncommon ones are offered with all three chosen: tapping one offers the swaps.
  await expect(p.getByText("In-clan disciplines (3 of 3)")).toBeVisible();
  await p.getByRole("checkbox", { name: "Protean" }).click();
  const room = p.getByRole("group", { name: "Make room for Protean" });
  await expect(room.getByRole("button", { name: /^Swap / })).toHaveCount(3);
  await room.getByRole("button", { name: "Swap Obfuscate for Protean" }).click();
  await expect(p.getByRole("checkbox", { name: "Protean" })).toBeChecked();
  await expect(p.getByRole("checkbox", { name: "Obfuscate" })).not.toBeChecked();
  await expect(p.getByText("Vestiges of Greatness: choose one")).toHaveCount(0);

  // The starting dot on Obfuscate moves to Protean, and the character finishes.
  await p.getByRole("link", { name: "Go to Disciplines" }).click();
  await expect(p.getByText("Your starting dot in Obfuscate needs moving: it is no longer in-clan. Clear it and place it on another.")).toBeVisible();
  await p.getByRole("button", { name: "Clear Obfuscate" }).click();
  await p.getByRole("button", { name: "Protean 1" }).click();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Merits & flaws", exact: true })).toBeVisible({ timeout: 15_000 });
  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Review/ }).click();
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
});

test("a Brujah takes Additional Uncommon Discipline on Merits, is held back until choosing it on Concept, and finishes", async ({ browser }) => {
  const { page: p } = await person(browser, "aud-finish");
  const id = await creatingVampire(p, "Second Skin", "Brujah", [], {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  await p.goto(`/characters/${id}/create/merits`);
  await p.getByLabel("Search Merits").fill("Additional Uncommon");
  await p.getByRole("checkbox", { name: /^Additional Uncommon Discipline/ }).check();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });

  const settle = p.getByRole("region", { name: "Still to settle" });
  await expect(settle).toContainText("Additional Uncommon Discipline: choose the in-clan discipline it adds. (p. 248)");
  await expect(p.getByText("Everything is placed. Settle what is listed above to finish.")).toBeVisible();
  await settle.getByRole("link", { name: "Go to Concept" }).click();

  // One slot, empty, with only the merit's list.
  await expect(p.getByText("In-clan disciplines (0 of 1)")).toBeVisible();
  await expect(p.getByRole("checkbox", { name: "Auspex" })).toHaveCount(0);
  await p.getByRole("checkbox", { name: "Quietus" }).click();
  await expect(p.getByRole("checkbox", { name: "Quietus" })).toBeChecked();
  await expect(p.getByText("In-clan now: Celerity, Potence, Presence and Quietus.")).toBeVisible();

  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Review/ }).click();
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
});

test("a Brujah takes Additional Uncommon Discipline from Concept and chooses Protean", async ({ browser }) => {
  const { page: p } = await person(browser, "aud-brujah");
  const id = await creatingVampire(p, "Roadkill", "Brujah", []);
  await p.goto(`/characters/${id}/create/concept`);
  await expect(p.getByText("In-clan now: Celerity, Potence and Presence.")).toBeVisible();
  const fromMerits = p.getByRole("region", { name: "From merits" });
  // Caitiff merits are not offered to a Brujah.
  await expect(fromMerits.getByRole("switch", { name: /^Vestiges of Greatness/ })).toHaveCount(0);
  await fromMerits.getByRole("switch", { name: /^Additional Uncommon Discipline/ }).click();
  await expect(fromMerits.getByRole("switch", { name: /^Additional Uncommon Discipline/ })).toBeChecked();
  await expect(p.getByText("One extra in-clan discipline from the uncommon ones (Additional Uncommon Discipline).")).toBeVisible();
  await expect(p.getByText("Additional Uncommon Discipline: choose the in-clan discipline it adds.")).toBeVisible();
  // Only the merit's list is offered.
  await expect(p.getByRole("checkbox", { name: "Auspex" })).toHaveCount(0);
  await p.getByRole("checkbox", { name: "Protean" }).click();
  await expect(p.getByRole("checkbox", { name: "Protean" })).toBeChecked();
  await expect(p.getByText("In-clan now: Celerity, Potence, Presence and Protean.")).toBeVisible();
  await expect(p.getByText("Additional Uncommon Discipline: choose the in-clan discipline it adds.")).toHaveCount(0);

  // On Merits, a merit refused for the clan says so, and links back to Concept.
  await p.goto(`/characters/${id}/create/merits`);
  await p.getByLabel("Show Merits").selectOption("Everything");
  await p.getByLabel("Search Merits").fill("Inceptor");
  const inceptor = p.locator("li").filter({ hasText: /^Inceptor/ });
  await expect(inceptor).toContainText("Refused while you are Brujah (Concept)");
  await inceptor.getByRole("link", { name: "Concept" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
});

/** Taps a button after bringing it to the middle of the screen, clear of the sticky counters on a phone. */
async function tapMid(p: Page, name: string) {
  const button = p.getByRole("button", { name });
  await button.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await button.click();
}

const CAITIFF_THREE = ["Auspex", "Celerity", "Potence"];

test("Thin Blooded taken after the Disciplines step shows the new budget there, and keeps the dot at 2 until it moves", async ({ browser }) => {
  const { page: p } = await person(browser, "thin-late");
  const id = await creatingVampire(p, "Watered Down", "Caitiff", CAITIFF_THREE, {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Auspex", 1], ["Potence", 1]],
  });
  await p.goto(`/characters/${id}/create/disciplines`);
  await expect(p.getByText("Starting disciplines are your in-clan ones: one at 2 and two at 1.")).toBeVisible();

  // Taken on Merits, after the dots were placed.
  await p.goto(`/characters/${id}/create/merits`);
  await p.getByLabel("Search Flaws").fill("Thin Blooded");
  await p.getByRole("checkbox", { name: /^Thin Blooded/ }).check();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });
  const settle = p.getByRole("region", { name: "Still to settle" });
  await expect(settle).toContainText("Thin Blooded: starting disciplines no longer have a pick at 2. Your dot in Celerity needs moving.");
  await settle.getByRole("link", { name: "Go to Disciplines" }).click();

  // Disciplines shows the new budget, and keeps the dot where it was, marked.
  await expect(p.getByText("Starting disciplines are your in-clan ones: two at 1 (Thin Blooded changes the usual).")).toBeVisible();
  await expect(p.getByRole("group", { name: "Changed by other steps" })).toContainText("Thin Blooded: starting disciplines no longer have a pick at 2.");
  await expect(p.getByRole("region", { name: "From merits and flaws" }).getByRole("switch", { name: /^Thin Blooded/ })).toBeChecked();
  await expect(p.getByRole("button", { name: "Celerity 2" })).toHaveAttribute("aria-pressed", "true");
  await expect(p.getByText("0 at 1 left")).toBeVisible();
  await expect(p.getByText("1 too many at 2")).toBeVisible();

  // Moving it: one dot in each of two. (Auspex goes, so Celerity can take the second dot.)
  await tapMid(p, "Clear Celerity");
  await tapMid(p, "Clear Potence");
  await tapMid(p, "Celerity 1");
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Merits & flaws", exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(p.getByRole("navigation", { name: "Creation steps" }).getByText("(needs a look)")).toHaveCount(0);
  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Review/ }).click();
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
});

test("Inept lets the player choose the discipline that loses its free dot, from the Disciplines step", async ({ browser }) => {
  const { page: p } = await person(browser, "inept-brujah");
  const id = await creatingVampire(p, "Clumsy Blood", "Brujah", [], {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  await p.goto(`/characters/${id}/create/disciplines`);
  const fromMerits = p.getByRole("region", { name: "From merits and flaws" });
  // Only the in-clan disciplines can be named.
  const choice = fromMerits.getByLabel("Inept: which?");
  await expect(choice.getByRole("option")).toHaveText(["Which?", "Celerity", "Potence", "Presence"]);
  await choice.selectOption("Presence");
  await fromMerits.getByRole("switch", { name: /^Inept/ }).click();
  await expect(fromMerits.getByRole("switch", { name: /^Inept/ })).toBeChecked();
  await expect(fromMerits.getByText("Presence")).toBeVisible();

  // One pick at 1 fewer, and the dot on Presence is kept, marked.
  await expect(p.getByText("Starting disciplines are your in-clan ones: one at 2 and one at 1 (Inept changes the usual).")).toBeVisible();
  await expect(p.getByText("Inept: Presence starts without a free dot, so your starting dot in it needs moving.").first()).toBeVisible();
  await expect(p.getByRole("button", { name: "Presence 1" })).toHaveAttribute("aria-pressed", "true");
  await expect(p.getByRole("button", { name: "Finish creation" })).toHaveCount(0);

  await tapMid(p, "Clear Presence");
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Merits & flaws", exact: true })).toBeVisible({ timeout: 15_000 });
  // Merits shows it as taken, from the flaws budget.
  await expect(p.getByRole("checkbox", { name: /^Inept/ })).toBeChecked();
  await expect(p.getByText("3 of 7 points")).toBeVisible();
  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Review/ }).click();
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();

  // Presence is priced out-of-clan now: a first dot costs what one of Auspex does.
  const firstDot = async (discipline: string) => {
    const cart = await p.request.post(`/api/characters/${id}/cart`, {
      headers: { "X-Horatio": "1" },
      data: { dry_run: true, changes: [{ kind: "set", category: "disciplines", name: discipline, rating: 1 }] },
    });
    expect(cart.status(), await cart.text()).toBe(200);
    return (await cart.json()).lines[0].cost;
  };
  expect(await firstDot("Presence")).toBe(await firstDot("Auspex"));
});

test("a path merit bought in creation starts the path at 4, and Review says so", async ({ browser }) => {
  const { page: p } = await person(browser, "path-start");
  const id = await creatingVampire(p, "Lost Faith", "Brujah", [], {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  await p.goto(`/characters/${id}/create/merits`);
  await p.getByLabel("Search Merits").fill("Path of Caine");
  await p.getByRole("checkbox", { name: /^Path of Caine/ }).check();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(p.getByRole("region", { name: "Morality" })).toContainText("Path of Caine: your path starts at 4");

  const morality = async () => {
    const sheet = await (await p.request.get(`/api/characters/${id}/sheet`)).json();
    return sheet.traits.filter((t: { category: string }) => t.category === "paths").map((t: { name: string; rating: number }) => [t.name, t.rating]);
  };
  expect(await morality()).toEqual([["Caine", 4]]);

  // Without the merit, Humanity is back at 5 and Review says nothing of it.
  await p.goto(`/characters/${id}/create/merits`);
  await p.getByLabel("Search Merits").fill("Path of Caine");
  await p.getByRole("checkbox", { name: /^Path of Caine/ }).click();
  await expect(p.getByRole("checkbox", { name: /^Path of Caine/ })).not.toBeChecked();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(p.getByRole("region", { name: "Morality" })).toHaveCount(0);
  expect(await morality()).toEqual([["Humanity", 5]]);
});

test("a fourth in-clan discipline from a merit shows on Disciplines as taking no free dot", async ({ browser }) => {
  const { page: p } = await person(browser, "fourth-dot");
  const id = await creatingVampire(p, "Four Of Them", "Brujah", []);
  await p.goto(`/characters/${id}/create/concept`);
  const fromMerits = p.getByRole("region", { name: "From merits" });
  await fromMerits.getByRole("switch", { name: /^Additional Common Discipline/ }).click();
  await expect(fromMerits.getByRole("switch", { name: /^Additional Common Discipline/ })).toBeChecked();
  await p.getByRole("checkbox", { name: "Auspex" }).click();
  await expect(p.getByRole("checkbox", { name: "Auspex" })).toBeChecked();

  await p.goto(`/characters/${id}/create/disciplines`);
  // It is in-clan, so priced as such, and listed, but takes no starting pick.
  await expect(p.getByText("In-clan now: Auspex, Celerity, Potence and Presence.")).toBeVisible();
  await expect(p.getByText("Additional Common Discipline: Auspex starts without a free dot.")).toBeVisible();
  await expect(p.getByRole("button", { name: "Auspex 1" })).toBeDisabled();
  await expect(p.getByRole("button", { name: "Celerity 2" })).toBeEnabled();
});

test("a Tremere takes Thaumaturgic Expertise from the Disciplines step, and the path it prices in-clan can take a starting dot", async ({ browser }) => {
  const { page: p } = await person(browser, "expert-tremere");
  const id = await creatingVampire(p, "Second Path", "Tremere", []);
  await p.goto(`/characters/${id}/create/disciplines`);
  const fromMerits = p.getByRole("region", { name: "From merits and flaws" });
  await expect(p.getByRole("button", { name: "Thaumaturgy: Path of Conjuring 1" })).toHaveCount(0);

  await fromMerits.getByLabel("Thaumaturgic Expertise: which?").selectOption("Thaumaturgy: Path of Conjuring");
  await fromMerits.getByRole("switch", { name: /^Thaumaturgic Expertise/ }).click();
  await expect(fromMerits.getByRole("switch", { name: /^Thaumaturgic Expertise/ })).toBeChecked();
  await expect(p.getByText(/In-clan now: .*Thaumaturgy: Path of Conjuring/)).toBeVisible();
  await expect(p.getByRole("button", { name: "Thaumaturgy: Path of Conjuring 1" })).toBeEnabled();
});

test("Versatile asks for its extra focus on Focuses, and a pick on the focus it names is free to place again", async ({ browser }) => {
  const { page: p } = await person(browser, "wf-versatile");
  const id = await creatingVampire(p, "Many Hands", "Brujah", [], ATTRIBUTES_AND_FOCUSES);
  await p.goto(`/characters/${id}/create/focuses`);
  const fromMerits = p.getByRole("region", { name: "From merits" });
  const versatile = fromMerits.getByRole("switch", { name: /^Versatile/ });
  // It cannot be taken until it is told which focus.
  await expect(versatile).toBeDisabled();
  // Wits is the Mental focus already picked, so the merit would give nothing: the pick is free to place again.
  await fromMerits.getByLabel("Versatile: which?").selectOption("Wits");
  await versatile.click();
  await expect(versatile).toBeChecked();
  const notices = p.getByRole("group", { name: "Changed by other steps" });
  await expect(notices).toContainText("Versatile makes Wits free: your pick on Wits can go elsewhere.");
  await expect(p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Focuses \(needs a look\)/ })).toBeVisible();

  // Another focus is the extra one: held, with no pick to place on it.
  await versatile.click();
  await expect(versatile).not.toBeChecked();
  await fromMerits.getByLabel("Versatile: which?").selectOption("Perception");
  await versatile.click();
  await expect(versatile).toBeChecked();
  await expect(p.getByText("Versatile gives you Perception free.")).toBeVisible();
  await expect(notices).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Perception 1" })).toBeDisabled();

  // Merits shows it as taken, from the same points.
  await p.goto(`/characters/${id}/create/merits`);
  await expect(p.getByRole("checkbox", { name: /^Versatile/ })).toBeChecked();
  await expect(p.getByText("3 of 7 points")).toBeVisible();
});

test("Extrasensory Perceptions, taken from Focuses, shows Perception as held there", async ({ browser }) => {
  const { page: p } = await person(browser, "wf-senses");
  const id = await creatingVampire(p, "Sharp Nose", "Nosferatu: Creeps", [], ATTRIBUTES_AND_FOCUSES);
  await p.goto(`/characters/${id}/create/focuses`);
  const fromMerits = p.getByRole("region", { name: "From merits" });
  await fromMerits.getByRole("switch", { name: /^Extrasensory Perceptions/ }).click();
  await expect(fromMerits.getByRole("switch", { name: /^Extrasensory Perceptions/ })).toBeChecked();
  await expect(p.getByText("Extrasensory Perceptions gives you Perception free.")).toBeVisible();
  // The usual Mental pick is still Wits, and no pick goes on the given focus.
  await expect(p.getByRole("button", { name: "Wits 1" })).toHaveAttribute("aria-pressed", "true");
  await expect(p.getByRole("button", { name: "Perception 1" })).toBeDisabled();
  await expect(p.getByRole("group", { name: "Changed by other steps" })).toHaveCount(0);
});

test("Personal Cult frees a Herd pick, which goes elsewhere, and the character finishes with Herd 5 free", async ({ browser }) => {
  const { page: p } = await person(browser, "wf-cult");
  const id = await creatingVampire(p, "Temple Keeper", "Followers of Set", [], {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Obfuscate", 2], ["Presence", 1], ["Serpentis", 1]],
  });
  await p.goto(`/characters/${id}/create/backgrounds`);
  const fromMerits = p.getByRole("region", { name: "From merits and flaws" });
  await fromMerits.getByLabel("Personal Cult: which?").selectOption("Herd");
  await fromMerits.getByRole("switch", { name: /^Personal Cult/ }).click();
  await expect(fromMerits.getByRole("switch", { name: /^Personal Cult/ })).toBeChecked();

  // The pick on Herd is kept, marked on its row, the stepper and the notice, and linked.
  const message = "Personal Cult makes Herd free: your pick on Herd can go elsewhere.";
  await expect(p.getByRole("group", { name: "Changed by other steps" })).toContainText(message);
  await expect(p.getByText(`${message} Clear it and place it on another.`)).toBeVisible();
  await expect(p.getByRole("button", { name: "Herd 3" })).toHaveAttribute("aria-pressed", "true");
  await expect(p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Backgrounds \(needs a look\)/ })).toBeVisible();

  // Review lists it too.
  await p.goto(`/characters/${id}/create/review`);
  await expect(p.getByRole("region", { name: "Still to settle" })).toContainText(message);
  await p.getByRole("region", { name: "Still to settle" }).getByRole("link", { name: "Go to Backgrounds" }).click();

  // The pick goes to Fame, and Herd is shown as held free.
  await tapMid(p, "Clear Herd");
  await tapMid(p, "Fame 3");
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Disciplines", exact: true })).toBeVisible({ timeout: 15_000 });
  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Backgrounds/ }).click();
  await expect(p.getByText("Personal Cult gives you Herd 5 free.")).toBeVisible();
  await expect(p.getByRole("button", { name: "Herd 3" })).toBeDisabled();
  await expect(p.getByRole("navigation", { name: "Creation steps" }).getByText("(needs a look)")).toHaveCount(0);

  await p.goto(`/characters/${id}/create/review`);
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  const herd = (await (await p.request.get(`/api/characters/${id}/sheet`)).json()).traits.find((t: { name: string }) => t.name === "Herd");
  expect([herd.rating, herd.free_rating]).toEqual([5, 5]);
});

test("Seasoned Traveler frees a pick on Survival, which goes to another skill", async ({ browser }) => {
  const { page: p } = await person(browser, "wf-traveler");
  const skills: [string, number][] = [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Survival", 1], ["Melee", 1]];
  const id = await creatingVampire(p, "Road Dog", "Gangrel", [], { ...ATTRIBUTES_AND_FOCUSES, skills });
  await p.goto(`/characters/${id}/create/skills`);
  const fromMerits = p.getByRole("region", { name: "From merits" });
  await fromMerits.getByLabel("Seasoned Traveler: which?").selectOption("Survival");
  await fromMerits.getByRole("switch", { name: /^Seasoned Traveler/ }).click();
  await expect(fromMerits.getByRole("switch", { name: /^Seasoned Traveler/ })).toBeChecked();
  await expect(p.getByText("Seasoned Traveler makes Survival free: your pick on Survival can go elsewhere. Clear it and place it on another.")).toBeVisible();

  // Moved to Medicine, it is held free at 3 and nothing is left to settle.
  await tapMid(p, "Clear Survival");
  await tapMid(p, "Medicine 1");
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Backgrounds", exact: true })).toBeVisible({ timeout: 15_000 });
  await p.goto(`/characters/${id}/create/skills`);
  await expect(p.getByText("Seasoned Traveler gives you Survival 3 free.")).toBeVisible();
  await expect(p.getByRole("navigation", { name: "Creation steps" }).getByText("(needs a look)")).toHaveCount(0);
});

test("Archaic names the Computer pick it clashes with on Merits, and Computer names Archaic on Skills", async ({ browser }) => {
  const { page: p } = await person(browser, "wf-archaic");
  const skills: [string, number][] = [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Computer", 1], ["Melee", 1]];
  const id = await creatingVampire(p, "Old Ways", "Brujah", [], { ...ATTRIBUTES_AND_FOCUSES, skills });
  await p.goto(`/characters/${id}/create/merits`);
  await p.getByLabel("Show Flaws").selectOption("Everything");
  await p.getByLabel("Search Flaws").fill("Archaic");
  const archaic = p.locator("li").filter({ hasText: /^Archaic/ });
  await expect(archaic).toContainText("An Archaic character cannot have Computer, Drive, Science or Security.");
  await expect(archaic).toContainText("Refused while you have Computer (Skills)");
  await expect(archaic.getByRole("checkbox")).toBeDisabled();
  await archaic.getByRole("link", { name: "Skills" }).click();
  await expect(p.getByRole("heading", { name: "Skills", exact: true })).toBeVisible();

  // Computer goes to Medicine, and Archaic can be taken.
  await tapMid(p, "Clear Computer");
  await tapMid(p, "Medicine 1");
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Backgrounds", exact: true })).toBeVisible({ timeout: 15_000 });
  await p.goto(`/characters/${id}/create/merits`);
  await p.getByLabel("Search Flaws").fill("Archaic");
  await p.getByRole("checkbox", { name: /^Archaic/ }).check();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });

  // Skills now says what bars Computer, and links to the flaw.
  await p.goto(`/characters/${id}/create/skills`);
  const computer = p.locator("li").filter({ has: p.getByRole("button", { name: "Computer 1" }) });
  await expect(computer).toContainText("An Archaic character cannot have Computer, Drive, Science or Security.");
  await expect(computer).toContainText("Because of Archaic");
  await expect(p.getByRole("button", { name: "Computer 1" })).toBeDisabled();
  await computer.getByRole("link", { name: "Merits & flaws" }).click();
  await expect(p.getByRole("heading", { name: "Merits & flaws", exact: true })).toBeVisible();
  await expect(p.getByRole("checkbox", { name: /^Archaic/ })).toBeChecked();
});

test("Childlike bars Physical 7 on Attributes, and Methuselah's Thirst bars Herd on Backgrounds, each naming the flaw", async ({ browser }) => {
  const { page: p } = await person(browser, "wf-clash");
  const id = await creatingVampire(p, "Small Hours", "Brujah", []);
  await p.goto(`/characters/${id}/create/merits`);
  await p.getByLabel("Search Flaws").fill("Childlike");
  await p.getByRole("checkbox", { name: /^Childlike/ }).check();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });

  await p.goto(`/characters/${id}/create/attributes`);
  const physical = p.locator("li").filter({ has: p.getByRole("button", { name: "Physical 7" }) });
  await expect(physical).toContainText("Not at 7: A Childlike character's Physical attribute cannot go above 5.");
  await expect(physical).toContainText("Because of Childlike");
  await expect(p.getByRole("button", { name: "Physical 7" })).toBeDisabled();
  await expect(p.getByRole("button", { name: "Physical 5" })).toBeEnabled();
  await expect(p.getByRole("button", { name: "Mental 7" })).toBeEnabled();
  await physical.getByRole("link", { name: "Merits & flaws" }).click();
  await expect(p.getByRole("checkbox", { name: /^Childlike/ })).toBeChecked();

  // Swapped for Methuselah's Thirst, it is Herd that is barred, on Backgrounds.
  await p.getByRole("checkbox", { name: /^Childlike/ }).uncheck();
  await p.getByLabel("Search Flaws").fill("Methuselah");
  await p.getByRole("checkbox", { name: /^Methuselah's Thirst/ }).check();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });
  await p.goto(`/characters/${id}/create/backgrounds`);
  const herd = p.locator("li").filter({ has: p.getByRole("button", { name: "Herd 1" }) });
  await expect(herd).toContainText("A character with Methuselah's Thirst cannot benefit from Herd.");
  await expect(herd).toContainText("Because of Methuselah's Thirst");
  await expect(p.getByRole("button", { name: "Herd 1" })).toBeDisabled();
  await herd.getByRole("link", { name: "Merits & flaws" }).click();
  await expect(p.getByRole("checkbox", { name: /^Methuselah's Thirst/ })).toBeChecked();
});

test("Lesser Generation on Backgrounds follows the Generation picked, and bars the dots it cannot go with", async ({ browser }) => {
  const { page: p } = await person(browser, "wf-lesser");
  const id = await creatingVampire(p, "Hand Me Down", "Brujah", [], { backgrounds: [["Fame", 3], ["Resources", 1], ["Generation", 2]] });
  await p.goto(`/characters/${id}/create/backgrounds`);
  const fromMerits = p.getByRole("region", { name: "From merits and flaws" });
  // What each one is, from the catalogue, and why one is refused for the Generation picked.
  await expect(fromMerits.getByRole("switch", { name: /^Lesser Generation 1/ })).toBeEnabled();
  await expect(fromMerits).toContainText("Neonate is of the 12th Generation, Ancilla is of the 10th Generation.");
  await expect(fromMerits.getByRole("switch", { name: /^Lesser Generation 2/ })).toBeDisabled();
  await expect(fromMerits).toContainText("Lesser Generation 2 is only for Neonate characters.");
  await expect(fromMerits).toContainText("Because of Generation");
  // Thin Blooded is for a Caitiff, so it is not offered to a Brujah.
  await expect(fromMerits.getByRole("switch", { name: /^Thin Blooded/ })).toHaveCount(0);

  await fromMerits.getByRole("switch", { name: /^Lesser Generation 1/ }).click();
  await expect(fromMerits.getByRole("switch", { name: /^Lesser Generation 1/ })).toBeChecked();
  // An Ancilla can have it; a third dot of Generation is an elder's, which it cannot go with.
  const generation = p.locator("li").filter({ has: p.getByRole("button", { name: "Generation 1" }) });
  await expect(generation).toContainText("Not at 3: Lesser Generation 1 is only for Neonate or Ancilla characters.");
  await expect(generation).toContainText("Because of Lesser Generation 1");
  await expect(p.getByRole("button", { name: "Generation 3" })).toBeDisabled();
  await expect(p.getByRole("button", { name: "Generation 2" })).toBeEnabled();
});

test("Thin Blooded on Backgrounds bars Generation above 1, and a Caitiff cannot have 3", async ({ browser }) => {
  const { page: p } = await person(browser, "wf-thinbl");
  const id = await creatingVampire(p, "Watery Blood", "Caitiff", ["Auspex", "Celerity", "Potence"], { backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]] });
  await p.goto(`/characters/${id}/create/backgrounds`);
  const generation = p.locator("li").filter({ has: p.getByRole("button", { name: "Generation 1" }) });
  await expect(generation).toContainText("Not at 3: Caitiff cannot have more than 2 dots of Generation.");
  await expect(generation).toContainText("Because of Caitiff (Concept)");
  await expect(p.getByRole("button", { name: "Generation 2" })).toBeEnabled();

  const fromMerits = p.getByRole("region", { name: "From merits and flaws" });
  await fromMerits.getByRole("switch", { name: /^Thin Blooded/ }).click();
  await expect(fromMerits.getByRole("switch", { name: /^Thin Blooded/ })).toBeChecked();
  await expect(fromMerits).toContainText("Neonate is of the 14th or 15th Generation and always Caitiff.");
  await expect(generation).toContainText("Not at 2 or 3");
  await expect(generation).toContainText("Because of Thin Blooded");
  await expect(p.getByRole("button", { name: "Generation 2" })).toBeDisabled();
  await expect(p.getByRole("button", { name: "Generation 1" })).toBeEnabled();
  // Lesser Generation cannot go with it.
  await expect(fromMerits.getByRole("switch", { name: /^Lesser Generation 1/ })).toBeDisabled();
  await expect(fromMerits).toContainText("Lesser Generation and Thin Blooded cannot be held together.");
});

test("a Ventrue takes Royalty in the wizard, is sent to Backgrounds, and places 4, 3 and 2 there", async ({ browser }) => {
  const { page: p } = await person(browser, "wf-royal");
  const id = await creatingVampire(p, "Crowned", "Ventrue", [], {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Dominate", 2], ["Fortitude", 1], ["Presence", 1]],
  });
  await p.goto(`/characters/${id}/create/merits`);
  await p.getByLabel("Search Merits").fill("Royalty");
  await p.getByRole("checkbox", { name: /^Ventrue Royalty/ }).check();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });

  // Nothing is chosen yet: Review lists it, linking to where the gift lands.
  const settle = p.getByRole("region", { name: "Still to settle" });
  await expect(settle).toContainText("Ventrue Royalty: choose the backgrounds it gives.");
  await settle.getByRole("link", { name: "Go to Backgrounds" }).click();
  await expect(p.getByRole("group", { name: "Changed by other steps" })).toContainText("Ventrue Royalty: choose the backgrounds it gives.");
  const royalty = p.getByRole("group", { name: "Free traits from Ventrue Royalty" });
  await royalty.getByLabel("4 dots in").selectOption("Contacts");
  await royalty.getByLabel("3 dots in").selectOption("Haven");
  await royalty.getByLabel("2 dots in").selectOption("Herd");
  await royalty.getByRole("button", { name: "Save choices" }).click();
  await expect(p.getByRole("group", { name: "Changed by other steps" })).toHaveCount(0);
  await expect(p.getByText("Ventrue Royalty gives you Contacts 4 free.")).toBeVisible();
  await expect(p.getByText("Ventrue Royalty gives you Haven 3 free.")).toBeVisible();
  await expect(p.getByText("Ventrue Royalty gives you Herd 2 free.")).toBeVisible();
  await expect(p.getByRole("button", { name: "Herd 1" })).toBeDisabled();
  await expect(p.getByRole("navigation", { name: "Creation steps" }).getByText("(needs a look)")).toHaveCount(0);

  // Merits shows the same choices, and they change freely until a troupe accepts the character.
  await p.goto(`/characters/${id}/create/merits`);
  const there = p.getByRole("group", { name: "Free traits from Ventrue Royalty" });
  await expect(there.getByLabel("4 dots in")).toHaveValue("Contacts");
  await there.getByLabel("4 dots in").selectOption("Allies");
  await there.getByRole("button", { name: "Save changes" }).click();
  await expect(p.getByRole("button", { name: "Save changes" })).toBeDisabled();

  await p.goto(`/characters/${id}/create/review`);
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  const sheet = await (await p.request.get(`/api/characters/${id}/sheet`)).json();
  const dots = Object.fromEntries(sheet.traits.filter((t: { category: string }) => t.category === "backgrounds").map((t: { name: string; rating: number; free_rating: number }) => [t.name, [t.rating, t.free_rating]]));
  expect(dots).toMatchObject({ Allies: [4, 4], Haven: [3, 3], Herd: [2, 2] });
});

test("a Cappadocian takes Chosen of Cappadocius in the wizard and chooses its specialisations on Skills", async ({ browser }) => {
  const { page: p } = await person(browser, "wf-cappa");
  const id = await creatingVampire(p, "Grave Scholar", "Cappadocians", [], {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Auspex", 2], ["Fortitude", 1], ["Necromancy: Mortis Path", 1]],
  });
  await p.goto(`/characters/${id}/create/merits`);
  await p.getByLabel("Search Merits").fill("Chosen of Cappadocius");
  await p.getByRole("checkbox", { name: /^Chosen of Cappadocius/ }).check();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });
  const settle = p.getByRole("region", { name: "Still to settle" });
  await expect(settle).toContainText("Chosen of Cappadocius: choose the lore specializations, languages and academics specializations it gives.");
  await settle.getByRole("link", { name: "Go to Skills" }).click();

  const chosen = p.getByRole("group", { name: "Free traits from Chosen of Cappadocius" });
  for (const heading of ["Lore Specializations", "Languages", "Academics Specializations"]) {
    for (const choice of [1, 2]) await chosen.getByLabel(`${heading}, choice ${choice}`).selectOption({ index: choice });
  }
  await chosen.getByRole("button", { name: "Save choices" }).click();
  await expect(p.getByRole("group", { name: "Changed by other steps" })).toHaveCount(0);
  const sheet = await (await p.request.get(`/api/characters/${id}/sheet`)).json();
  const given = sheet.traits.filter((t: { category: string; granted_rating: number }) => t.category.endsWith("_specializations") && t.granted_rating > 0);
  expect(given).toHaveLength(6);
});

test("a player makes up an archetype in the creation wizard, and it shows on the sheet and the printed sheet", async ({ browser }) => {
  const { page } = await person(browser, "penitent");
  await page.getByLabel("Name").fill("Dismas");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  const id = page.url().match(/characters\/([0-9a-f-]{36})/)![1];
  await page.getByLabel("Archetype", { exact: true }).selectOption("Other…");
  // It waits for a name before it can be saved.
  await expect(page.getByRole("button", { name: "Save archetype" })).toBeDisabled();
  await page.getByLabel("Archetype's name").fill("The Penitent Thief");
  await page.getByLabel("What it means for the character").fill("Steals only to give back.");
  await page.getByRole("button", { name: "Save archetype" }).click();
  // The name given stands in the page title, with the description in the ⓘ beside it…
  await expect(page.getByText("The Penitent Thief", { exact: true })).toBeVisible();
  const info = page.getByRole("button", { name: "About The Penitent Thief" });
  await info.click();
  await expect(page.locator(`[id="${await info.getAttribute("aria-controls")}"]`)).toContainText("Steals only to give back.");
  // …and survives a reload.
  await page.reload();
  await expect(page.getByLabel("Archetype's name")).toHaveValue("The Penitent Thief");
  // The printed sheet gives the name too.
  await page.goto(`/print/characters/${id}`);
  await expect(page.getByText("The Penitent Thief", { exact: true })).toBeVisible();
});

test("a merit taken in the creation wizard gives the traits it grants", async ({ browser }) => {
  const { page: p } = await person(browser, "creep");
  await p.getByLabel("Name").fill("Grub");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  await p.getByLabel("Clan").selectOption("Nosferatu: Creeps");
  await expect(p.getByLabel("Clan")).toHaveValue("Nosferatu: Creeps");
  // Every pick but the merits placed through the API.
  const id = new URL(p.url()).pathname.split("/")[2]!;
  const build: Record<string, [string, number][]> = {
    attributes: [["Mental", 7], ["Physical", 5], ["Social", 3]],
    focus_physicals: [["Dexterity", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Manipulation", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Obfuscate", 2], ["Animalism", 1], ["Auspex", 1]],
  };
  for (const [category, picks] of Object.entries(build)) {
    const response = await p.request.put(`/api/characters/${id}/creation/categories/${category}`, {
      headers: { "X-Horatio": "1" },
      data: { picks: picks.map(([name, rating]) => ({ name, rating })) },
    });
    expect(response.status(), await response.text()).toBe(200);
  }

  await p.goto(`/characters/${id}/create/merits`);
  await expect(p.getByRole("heading", { name: "Merits & flaws", exact: true })).toBeVisible();
  await p.getByLabel("Search Merits").fill("Extrasensory");
  await p.getByRole("checkbox", { name: /^Extrasensory Perceptions/ }).check();
  await p.getByRole("button", { name: "Save and continue" }).click();
  // Saving waits for the lists of what can be taken to reload, which takes a while with both browsers at it.
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });
  // Only the merit's own point comes from the budget.
  await expect(p.getByText("Extrasensory Perceptions (1 of 7 points)")).toBeVisible();
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  // The sheet shows the creation card until the finished character reloads, and it lists Wits too.
  await expect(p.getByRole("heading", { name: "Character creation" })).toHaveCount(0);

  // Acute Sense for hearing and for smell, and the Perception focus beside Wits, all marked as given by the merit.
  const row = (text: string | RegExp) => p.locator("main li").filter({ hasText: text });
  await expect(row("Acute Sense: Hearing")).toContainText("from Extrasensory Perceptions");
  await expect(row("Acute Sense: Smell")).toContainText("from Extrasensory Perceptions");
  await expect(row(/^Perception\b/)).toContainText("+1 from Extrasensory Perceptions");
  await expect(row("Wits")).toBeVisible();
  // Given, not bought: neither can be taken off on its own.
  await expect(p.getByRole("button", { name: "Remove Acute Sense" })).toHaveCount(0);
});

test("a Ventrue takes Royalty from the sheet, places 4, 3 and 2 free dots, changes them until a troupe accepts the character, and not after", async ({ browser }) => {
  const custodian = await person(browser, "royal-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "royal-lead");
  const player = await person(browser, "royal-player");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of the Crown ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;

  // Cordelia, a finished Ventrue with two dots of Resources bought (3 XP at a Neonate's prices).
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Cordelia" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Ventrue", rating: null });
  const build: Record<string, [string, number][]> = {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Contacts", 2], ["Generation", 1]],
    disciplines: [["Dominate", 2], ["Fortitude", 1], ["Presence", 1]],
  };
  for (const [category, picks] of Object.entries(build))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});
  await send("PUT", `/api/characters/${id}/traits`, { category: "backgrounds", name: "Resources", rating: 2 });
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  const trait = (name: string) => p.locator(`li[data-trait="${name}"]`);
  const chosen = p.locator('[data-free-choices="Ventrue Royalty"]');

  // The Add panel asks for the choices as the merit goes in: 4 in Resources, 3 in Herd, 2 in Allies.
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Merits").fill("Ventrue Royalty");
  await p.getByRole("button", { name: /^Ventrue Royalty/ }).click();
  await expect(p.getByText("Choose your free backgrounds")).toBeVisible();
  await expect(p.getByText("Place 4, 3 and 2 dots, each in a different one.")).toBeVisible();
  await p.getByLabel("4 dots in").selectOption("Resources");
  await p.getByLabel("3 dots in").selectOption("Herd");
  await p.getByLabel("2 dots in").selectOption("Allies");
  // A background can be placed once: Resources is taken.
  await expect(p.getByLabel("3 dots in").getByRole("option", { name: "Resources" })).toBeDisabled();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Add Ventrue Royalty" })).toContainText("free: Resources 4, Herd 3, Allies 2");
  await p.getByRole("button", { name: "Spend XP" }).click();

  // The dots are free ones, and the 3 XP paid for Resources is back (2 XP for the merit, less 3).
  await expect(trait("Resources")).toContainText("+4 from Ventrue Royalty");
  await expect(trait("Herd")).toContainText("+3 from Ventrue Royalty");
  await expect(trait("Allies")).toContainText("+2 from Ventrue Royalty");
  await expect(chosen).toContainText("Resources 4");
  await expect(chosen).toContainText("Herd 3");
  await expect(chosen).toContainText("Allies 2");
  await expect(p.getByText("28", { exact: true })).toBeVisible();
  await p.screenshot(shots("royalty-placed"));

  // Until a troupe accepts her, the choices change freely: Haven in place of Resources.
  await p.getByRole("button", { name: "Change the free traits for Ventrue Royalty" }).click();
  await p.getByLabel("4 dots in").selectOption("Haven");
  await p.getByRole("button", { name: "Save", exact: true }).click();
  await expect(trait("Haven")).toContainText("+4 from Ventrue Royalty");
  await expect(trait("Resources")).toHaveCount(0);
  await expect(chosen).toContainText("Haven 4");

  // The lead sees what she chose where the request is accepted.
  await send("POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/approvals`);
  const card = l.locator("section").filter({ hasText: "Cordelia" });
  await expect(card).toContainText("Free traits the player chose");
  await expect(card).toContainText("Ventrue Royalty: Haven 4, Herd 3, Allies 2");
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();

  // Once accepted, they are staff's to change.
  await p.reload();
  await expect(chosen).toContainText("Haven 4");
  await expect(chosen).toContainText("can't change once a home troupe has accepted");
  await expect(p.getByRole("button", { name: "Change the free traits for Ventrue Royalty" })).toHaveCount(0);
  const refused = await p.request.fetch(`/api/characters/${id}/traits/choices`, {
    method: "PUT",
    headers,
    data: { category: "merits", name: "Ventrue Royalty", detail: "", picks: [] },
  });
  expect(refused.status()).toBe(409);
});

test("changes on the sheet wait in a cart, and only Spend XP makes them, all or none", async ({ browser }) => {
  const { page: p } = await person(browser, "carter");
  await p.getByLabel("Name").fill("Wren");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  // Built through the API all but one pick, which is placed from the sheet.
  const id = new URL(p.url()).pathname.split("/")[2]!;
  const put = async (url: string, data: object) => {
    const response = await p.request.put(url, { headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBe(200);
  };
  await put(`/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const build: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1]],
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, picks] of Object.entries(build))
    await put(`/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const cart = p.getByRole("list", { name: "Changes in the cart" });

  // Creation picks go through the cart too: placing one, and taking one back.
  await p.getByLabel("Pick Skills at 1").selectOption("Melee");
  await p.getByRole("button", { name: "Take back the pick on Medicine" }).click();
  await p.getByLabel("Pick Skills at 1").selectOption("Stealth");
  await expect(cart.getByRole("listitem")).toHaveText([/Take back the pick on Medicine/, /Pick Melee at 1/, /Pick Stealth at 1/]);
  await expect(p.getByRole("button", { name: "Apply picks" })).toBeEnabled();
  // The cart is kept in this browser, and leaving the page with it full asks first.
  const asked = p.waitForEvent("dialog");
  const reloaded = p.reload();
  const leaving = await asked;
  expect(leaving.type()).toBe("beforeunload");
  await leaving.accept();
  await reloaded;
  await expect(cart.getByRole("listitem")).toHaveCount(3);
  // Finishing with picks still in the cart asks what to do with them.
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByText("3 changes in the cart are not applied yet.", { exact: false })).toBeVisible();
  await p.getByRole("button", { name: "Apply them and finish" }).click();
  await expect(p.getByRole("heading", { name: "Character creation" })).toHaveCount(0);
  await expect(part("Skills").getByText("Stealth")).toBeVisible();
  await expect(part("Skills").getByText("Medicine")).toHaveCount(0);

  // Two dots of Dodge, priced dot by dot: nothing is spent yet, and the sheet shows what it would be.
  await p.getByRole("button", { name: "Raise Dodge" }).click();
  await p.getByRole("button", { name: "Raise Dodge" }).click();
  await expect(cart.getByText("Dodge 3 → 5 · 9 XP")).toBeVisible();
  await expect(p.getByLabel("3 dots, 5 after the changes in the cart")).toHaveText("3 → 5");
  await expect(p.getByText("after these changes", { exact: true })).toBeVisible();
  await expect(p.getByText("21", { exact: true })).toBeVisible();
  // Lowering it again steps the cart back.
  await p.getByRole("button", { name: "Lower Dodge" }).click();
  await expect(cart.getByText("Dodge 3 → 4 · 4 XP")).toBeVisible();
  await p.getByRole("button", { name: "Raise Dodge" }).click();

  // Archaic, then Computer, which an Archaic character cannot have: Archaic's line is refused, and nothing can be spent.
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  await p.getByRole("navigation", { name: "Categories" }).getByRole("button", { name: /^Flaws/ }).click();
  await p.getByLabel("Search Flaws").fill("Archaic");
  await p.getByRole("button", { name: /^Archaic/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await part("Skills").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Skills").fill("Computer");
  await p.getByRole("button", { name: /^Computer/ }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Add Archaic" })).toContainText("An Archaic character cannot have Computer");
  await expect(cart.getByRole("listitem").filter({ hasText: "Add Computer 1" })).not.toContainText("cannot have");
  await expect(p.getByRole("button", { name: "Spend XP" })).toBeDisabled();
  await expect(p.getByText("A change can't be made; see the line marked.")).toBeVisible();
  if (test.info().project.name === "phone") {
    // Below the sheet on a phone, the cart is a tap away from the bar at the foot of the screen.
    await p.getByRole("button", { name: "3 changes · 8 XP · Review" }).click();
    await expect(p.getByRole("button", { name: "Spend XP" })).toBeInViewport();
  }
  await p.screenshot(shots("cart"));
  await p.getByRole("button", { name: "Take Add Computer 1 out of the cart" }).click();
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 7 XP.")).toBeVisible(); // 9 for Dodge, less 2 for Archaic
  await expect(p.getByText("23", { exact: true })).toBeVisible();
  await expect(p.locator("li", { has: p.getByRole("button", { name: "Raise Dodge" }) }).getByLabel("5 dots", { exact: true })).toHaveText("5");
  await p.locator("main").getByRole("link", { name: "Experience", exact: true }).click();
  await expect(p.getByText("Dodge 3 → 5")).toBeVisible();
});

test("the sheet says what a trait does, under its name, and what a heading is, in an ⓘ", async ({ browser }) => {
  const { page: p } = await person(browser, "annotator");
  await p.getByLabel("Name").fill("Marginalia");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const id = new URL(p.url()).pathname.split("/")[2]!;
  const put = async (url: string, data: object) => {
    const response = await p.request.put(url, { headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBe(200);
  };
  await put(`/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  await put(`/api/characters/${id}/creation/categories/skills`, { picks: [{ name: "Brawl", rating: 2 }] });
  await put(`/api/characters/${id}/creation/categories/backgrounds`, { picks: [{ name: "Generation", rating: 1 }] });
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const fits = async (name: string) => {
    const box = (await p.getByText(name).boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(p.viewportSize()!.width);
  };

  // A skill opens to its description under the row, and closes again; the dots stay where they were.
  const brawl = part("Skills").getByRole("button", { name: "Brawl", exact: true });
  const about = p.getByText("Fighting with your body: fists, feet, grapples and claws.");
  await expect(brawl).toHaveAttribute("aria-expanded", "false");
  await expect(about).toHaveCount(0);
  await brawl.click();
  await expect(brawl).toHaveAttribute("aria-expanded", "true");
  await expect(about).toBeVisible();
  await expect(part("Skills").getByLabel("2 dots")).toBeVisible();
  await p.screenshot(shots("trait-info"));
  // A background with a book page gives it; several stay open together.
  const generation = part("Backgrounds").getByRole("button", { name: "Generation", exact: true });
  await generation.click();
  await expect(p.getByText("MET: VTM pp. 100-102")).toBeVisible();
  await expect(about).toBeVisible();
  await brawl.click();
  await expect(brawl).toHaveAttribute("aria-expanded", "false");
  await expect(about).toHaveCount(0);

  // A heading's ⓘ opens a small popover, closed by pressing it again, pressing outside, or Escape.
  const skills = part("Skills").getByRole("button", { name: "About Skills" });
  const words = p.getByText("What the character has learned to do");
  await skills.click();
  await expect(words).toBeVisible();
  await fits("What the character has learned to do");
  await skills.click();
  await expect(words).toHaveCount(0);
  await skills.click();
  await p.keyboard.press("Escape");
  await expect(words).toHaveCount(0);
  await expect(skills).toBeFocused();
  await skills.click();
  await expect(words).toBeVisible();
  await p.getByRole("heading", { name: "Marginalia" }).click();
  await expect(words).toHaveCount(0);

  // So does a choice in the page title, with the clan's in-clan disciplines.
  const clan = p.getByRole("button", { name: "About Brujah" });
  await clan.click();
  await expect(p.getByText("In-clan disciplines: Celerity, Potence, Presence.")).toBeVisible();
  await fits("In-clan disciplines: Celerity, Potence, Presence.");
  await p.screenshot(shots("clan-info"));
  await p.keyboard.press("Escape");
  await expect(p.getByText("In-clan disciplines: Celerity, Potence, Presence.")).toHaveCount(0);
});

test("the Play View's Sheet tab puts the archetype in the subheader, and says what each trait does", async ({ browser }) => {
  const { page: p } = await person(browser, "play-glossary");
  await p.getByLabel("Name").fill("Footnote");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const id = new URL(p.url()).pathname.split("/")[2]!;
  const put = async (url: string, data: object) => {
    const response = await p.request.put(url, { headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBe(200);
  };
  await put(`/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  await put(`/api/characters/${id}/traits`, { category: "archetype", name: "Loner", rating: null });
  await put(`/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
  await put(`/api/characters/${id}/creation/categories/skills`, { picks: [{ name: "Athletics", rating: 2 }] });
  await put(`/api/characters/${id}/creation/categories/backgrounds`, { picks: [{ name: "Generation", rating: 1 }] });
  await p.goto(`/play/characters/${id}?tab=sheet`);
  await expect(p.getByRole("heading", { name: "Footnote" })).toBeVisible();

  // The clan, archetype and sect are in the subheader, each with an ⓘ, and have no panels of their own.
  await expect(p.getByText("Loner", { exact: true })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Skills" })).toBeVisible();
  for (const part of ["Archetype", "Clan", "Sect"]) await expect(p.getByRole("heading", { name: part, exact: true })).toHaveCount(0);
  await p.getByRole("button", { name: "About Loner" }).click();
  await expect(p.getByText("You can't work within the system.")).toBeVisible();
  await expect(p.getByText("MET: VTM p. 87")).toBeVisible();
  await p.keyboard.press("Escape");
  await p.getByRole("button", { name: "About Brujah" }).click();
  await expect(p.getByText("In-clan disciplines: Celerity, Potence, Presence.")).toBeVisible();
  await p.keyboard.press("Escape");

  // A skill opens to what it lets you do, from the book, with the page.
  await p.getByRole("button", { name: "Athletics", exact: true }).click();
  await expect(p.getByText("Swimming, climbing and jumping are simple actions for you")).toBeVisible();
  await expect(p.getByText("MET: VTM p. 92")).toBeVisible();
  // So does a background, and both stay open.
  await p.getByRole("button", { name: "Generation", exact: true }).click();
  await expect(p.getByText("MET: VTM pp. 100-102")).toBeVisible();
  await expect(p.getByText("Swimming, climbing and jumping are simple actions for you")).toBeVisible();
  await p.screenshot(shots("play-sheet-info"));
});

test("a cart is judged by the sheet it ends with, so a technique may go in before what it needs", async ({ browser }) => {
  const { page: p } = await person(browser, "tactician");
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Kestrel" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
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
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});

  // Fearful Blow (Potence 2 and Presence 2) is in the cart before the dots it needs, as a cart kept from an earlier visit might be.
  const lines = [
    { kind: "set", category: "techniques", name: "Fearful Blow", detail: "", from: 0, to: 1, fixed: true },
    { kind: "set", category: "disciplines", name: "Potence", detail: "", from: 1, to: 2 },
    { kind: "set", category: "disciplines", name: "Presence", detail: "", from: 1, to: 2 },
  ];
  await p.evaluate(([key, value]) => localStorage.setItem(key, value), [`horatio.cart.${id}`, JSON.stringify(lines)]);
  await p.goto(`/characters/${id}`);
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  // Each line is priced as if the ones above it were made, and none is refused.
  await expect(cart.getByRole("listitem")).toHaveText([/Add Fearful Blow.* · 12 XP/, /Potence 1 → 2 · 6 XP/, /Presence 1 → 2 · 6 XP/]);
  await expect(p.getByText("A change can't be made; see the line marked.")).toHaveCount(0);

  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 24 XP.")).toBeVisible();
  await expect(p.locator("main").getByText("Fearful Blow", { exact: true })).toBeVisible();
});

test("a player fills in their profile, and the custodian resets their password", async ({ browser }) => {
  const custodian = await person(browser, "people-custodian");
  makeCustodian(custodian.email);
  const player = await person(browser, "people-player");

  // The player fills in their profile from their name in the header.
  const p = player.page;
  await p.getByRole("link", { name: "people-player" }).click();
  await expect(p.getByRole("heading", { name: "Your account" })).toBeVisible();
  await p.getByLabel("Bio").fill("Playing since the Masquerade was young.");
  await p.getByLabel("Discord username").fill("@Carbuncle_Fan");
  await p.getByRole("button", { name: "Add a link" }).click();
  await p.getByLabel("Label").fill("Bluesky");
  await p.getByLabel("Address").fill("https://bsky.app/profile/carbuncle.example");
  await p.getByRole("button", { name: "Save profile" }).click();
  await expect(p.getByText("Saved.")).toBeVisible();

  // The custodian finds them in Custodian → People and makes a reset link without
  // leaving the list. Email is off in this suite, so the link is there to copy.
  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "People", exact: true }).click();
  await c.getByLabel("Search people").fill(player.email);
  const row = c.locator("main li").filter({ hasText: player.email });
  await expect(row.getByText(`@${player.handle} · ${player.email}`, { exact: false })).toBeVisible();
  await row.getByRole("button", { name: "Reset password for people-player" }).click();
  await expect(row.getByText("Send it to them yourself.")).toBeVisible();
  await row.getByRole("button", { name: "Make a reset link" }).click();
  const cancelled = await row.getByLabel("Reset link", { exact: true }).inputValue();
  expect(cancelled).toContain("/reset-password/");
  await expect(row.getByText(/^people-player has a reset link, unused, until /)).toBeVisible();
  await expect(row.getByText("reset link out")).toBeVisible();
  const resets = c.locator("section", { has: c.getByRole("heading", { name: "Password resets" }) });
  await expect(resets.getByRole("button", { name: "Cancel people-player's reset link" }).first()).toBeVisible();
  await expect(resets.getByText("people-custodian made a password reset link for people-player.").first()).toBeVisible();
  await c.screenshot(shots("people-reset"));

  // They think better of it and cancel it.
  await row.getByRole("button", { name: "Cancel link" }).click();
  await expect(row.getByText("Make a link that lets people-player set a new password", { exact: false })).toBeVisible();
  await expect(row.getByText("reset link out")).toHaveCount(0);

  // They open the profile.
  await c.locator("main").getByRole("link", { name: new RegExp(player.email) }).click();
  await expect(c.getByRole("heading", { name: "people-player" })).toBeVisible();
  await expect(c.getByText(new RegExp(`^@${player.handle} · Member since .+\\(new this month\\)$`))).toBeVisible();
  await expect(c.getByText("Playing since the Masquerade was young.")).toBeVisible();
  await expect(c.getByText("@carbuncle_fan")).toBeVisible();
  await expect(c.getByRole("link", { name: "bsky.app/profile/carbuncle.example" })).toBeVisible();
  await c.screenshot(shots("profile"));

  // …and makes a new link there, which the player uses from a fresh browser. The
  // cancelled one no longer works.
  await c.getByRole("button", { name: "Make a reset link" }).click();
  const url = await c.getByLabel("Reset link", { exact: true }).inputValue();
  expect(url).toContain("/reset-password/");
  const fresh = await (await browser.newContext()).newPage();
  await fresh.goto(new URL(cancelled).pathname);
  await expect(fresh.getByText("This reset link has expired or been used.")).toBeVisible();
  await fresh.goto(new URL(url).pathname);
  await expect(fresh.getByText(`For people-player (${player.email})`)).toBeVisible();
  await fresh.getByLabel("New password").fill("a brand new password");
  await fresh.getByRole("button", { name: "Set password and sign in" }).click();
  await expect(fresh.getByRole("heading", { name: "Your characters" })).toBeVisible();

  // The old session has ended, and the link is spent.
  await p.goto("/characters");
  await expect(p.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await p.goto(new URL(url).pathname);
  await expect(p.getByText("This reset link has expired or been used.")).toBeVisible();
  await p.screenshot(shots("reset-spent"));

  // "Forgot your password?" needs email; without it, the page says to ask the custodian.
  await p.getByRole("link", { name: "Back to sign in" }).click();
  await p.getByRole("link", { name: "Forgot your password?" }).click();
  await expect(p.getByText("Horatio can't send email here, so ask the custodian to make you a reset link.")).toBeVisible();
  await p.screenshot(shots("forgot"));

  // The custodian sees who reset their password, and when.
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await expect(c.getByText("people-player set a new password with a reset link.").first()).toBeVisible();
  await expect(c.getByText("people-custodian cancelled people-player's reset link.").first()).toBeVisible();
  await c.screenshot(shots("password-resets"));
});

test("the custodian filters People by the troupe a player's active character is home in", async ({ browser }) => {
  const custodian = await person(browser, "tpf-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tpf-lead");
  const alpha = await person(browser, "tpf-alpha");
  const beta = await person(browser, "tpf-beta");
  const visitor = await person(browser, "tpf-visitor");
  const northName = `Court of Frost ${run}`;
  const southName = `Court of Ashfall ${run}`;

  const send = async (p: Page, method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const north = await send(custodian.page, "POST", "/api/troupes", { name: northName, lead_handle: lead.handle });
  const south = await send(custodian.page, "POST", "/api/troupes", { name: southName, lead_handle: lead.handle });

  // Alpha's character is accepted by the first troupe, beta's by the second. The
  // visitor only visits the first.
  const home = async (player: { page: Page }, name: string, troupeId: string) => {
    const id = await builtVampire(player.page, name, "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] });
    const approval = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
    await send(lead.page, "POST", `/api/approvals/${approval.id}/approve`, {});
    return id;
  };
  await home(alpha, "Frostbitten", north.id);
  await home(beta, "Emberling", south.id);
  const wanderer = await builtVampire(visitor.page, "Wanderer", "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] });
  await send(visitor.page, "POST", `/api/characters/${wanderer}/troupes`, { troupe_id: north.id });

  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "People", exact: true }).click();
  const list = c.locator("main li");
  const filter = c.getByLabel("Active character in");
  await expect(filter.locator("option").first()).toHaveText("Any troupe");

  await filter.selectOption({ label: northName });
  await expect(list.filter({ hasText: alpha.email })).toBeVisible();
  await expect(list.filter({ hasText: beta.email })).toHaveCount(0);
  await expect(list.filter({ hasText: visitor.email })).toHaveCount(0);
  await c.screenshot(shots("people-by-troupe"));

  // The search narrows it further: both apply.
  await c.getByLabel("Search people").fill(beta.email);
  await expect(c.getByText("No one matches.")).toBeVisible();
  await filter.selectOption({ label: southName });
  await expect(list.filter({ hasText: beta.email })).toBeVisible();
  await expect(list.filter({ hasText: alpha.email })).toHaveCount(0);

  await filter.selectOption({ label: "Any troupe" });
  await c.getByLabel("Search people").fill(visitor.email);
  await expect(list.filter({ hasText: visitor.email })).toBeVisible();
});

test("storytellers filter the troupe's characters and print what they find", async ({ browser }) => {
  const custodian = await person(browser, "filter-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "filter-lead");
  const troupeName = `Court of Mirrors ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Three NPCs, made straight through the API (the builder has its own test).
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  for (const [name, clan, occult] of [
    ["Prince", "Ventrue", 4],
    ["Mara", "Tremere", 1],
    ["Nell", "Giovanni", 0],
  ] as const) {
    const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(made.status(), await made.text()).toBe(201);
    const id = (await made.json()).id;
    const rate = (category: string, trait: string, rating: number | null) =>
      p.request.put(`/api/characters/${id}/npc/ratings`, { headers, data: { category, name: trait, rating, detail: "" } });
    expect((await rate("clan", clan, null)).status()).toBe(200);
    if (occult) expect((await rate("skills", "Occult", occult)).status()).toBe(200);
  }

  await p.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await expect(p.getByText("3 of 3 characters")).toBeVisible();
  await expect(p.getByRole("button", { name: "Remove “Is active”" })).toBeVisible(); // retired characters are hidden by default

  // Occult below 3, and (Tremere, or the Giovanni family).
  await p.getByRole("button", { name: "Filter" }).click();
  await p.getByRole("button", { name: "+ Condition", exact: true }).click();
  const occult = p.getByRole("group", { name: "Condition" }).nth(1);
  await occult.getByLabel("Category").selectOption({ label: "Skills" });
  await occult.getByLabel("Trait").selectOption("Occult");
  await occult.getByLabel("How").selectOption({ label: "below" });
  await occult.getByLabel("Number").fill("3");
  await expect(p.getByText("2 of 3 characters")).toBeVisible();
  await p.getByRole("button", { name: "+ Group" }).click();
  await p.getByLabel("Group match").selectOption({ label: "any of these (or)" });
  const tremere = p.getByRole("group", { name: "Condition" }).nth(2);
  await tremere.getByLabel("Value").selectOption("Tremere");
  await p.getByRole("button", { name: "Add a condition to this group" }).click();
  const giovanni = p.getByRole("group", { name: "Condition" }).nth(3);
  await giovanni.getByLabel("What").selectOption({ label: "Clan, sect, focus…" });
  await giovanni.getByLabel("How").selectOption({ label: "is in the family of" });
  await giovanni.getByLabel("Value").selectOption("Giovanni");
  await expect(p.getByText("2 of 3 characters")).toBeVisible();
  await expect(p.getByText("(Clan is Tremere, or Clan is in the Giovanni family)")).toBeVisible();
  const list = p.locator("main ul.divide-y");
  await expect(list.getByRole("link", { name: "Prince" })).toHaveCount(0);
  await expect(list.getByText("Occult 1")).toBeVisible(); // the number the filter compares
  await expect(list.getByText("Occult 0")).toBeVisible();
  await p.screenshot(shots("filter"));

  // The filter is in the URL, so it survives a reload.
  await p.reload();
  await expect(p.getByText("2 of 3 characters")).toBeVisible();

  // Print all prints what the filter shows.
  const printTab = p.context().waitForEvent("page");
  await p.getByRole("button", { name: "Print all 2" }).click();
  const printed = await printTab;
  await expect(printed.getByText("2 sheets", { exact: true })).toBeVisible();
  await printed.close();
});

test("someone asks for a troupe of their own, and the custodian approves it", async ({ browser }) => {
  const custodian = await person(browser, "requests-custodian");
  makeCustodian(custodian.email);
  const asker = await person(browser, "requests-asker");
  const troupeName = `Court of Cinders ${run}`;

  const a = asker.page;
  await a.getByRole("link", { name: "Troupes" }).click();
  await a.getByLabel("Troupe name").fill(troupeName);
  await a.getByLabel("Note to the custodian").fill("Eight players ready.");
  await a.getByRole("button", { name: "Send request" }).click();
  const mine = a.getByRole("listitem").filter({ hasText: troupeName });
  await expect(mine.getByText("Waiting", { exact: true })).toBeVisible();

  // It waits on the custodian's bell and under Custodian → Troupe requests.
  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: /Troupe requests/ }).click();
  const request = c.getByRole("listitem").filter({ hasText: troupeName });
  await expect(request.getByText("Eight players ready.")).toBeVisible();
  await c.screenshot(shots("troupe-request"));
  await request.getByRole("button", { name: "Approve and make the troupe" }).click();
  await expect(c.getByRole("link", { name: troupeName })).toBeVisible();

  // What is running, and that the database is on its latest migration.
  await c.getByRole("link", { name: "System", exact: true }).click();
  await expect(c.getByText("Up to date", { exact: true })).toBeVisible();
  await c.screenshot(shots("custodian-system"));

  // The asker now leads it.
  await a.reload();
  await expect(mine.getByText("Approved", { exact: true })).toBeVisible();
  await a.locator("main").getByRole("link", { name: troupeName }).first().click();
  await expect(a.getByText("Lead Storyteller").first()).toBeVisible();
});

test("a player renames their character once in three months, and the custodian any time", async ({ browser }) => {
  const custodian = await person(browser, "rename-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "rename-lead");
  const player = await person(browser, "rename-player");
  const troupeName = `Court of Lanterns ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Before any troupe has the character, renaming it is the player's own business.
  const p = player.page;
  await p.getByLabel("Name").fill("Agnes Moreau");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const rename = async (page: Page, from: string, to: string) => {
    await page.getByRole("button", { name: `More for ${from}` }).click();
    await page.getByRole("menuitem", { name: "Rename…" }).click();
    await page.getByLabel("New name").fill(to);
    await page.getByRole("button", { name: "Rename", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(to);
    await expect(page.getByRole("heading", { name: `Rename ${from}` })).toHaveCount(0);
  };
  await rename(p, "Agnes Moreau", "Agnes Bisset");
  await rename(p, "Agnes Bisset", "Agnes Moreau");

  // In a troupe, once every three months, and the troupe's storytellers are told.
  await p.locator("main").getByRole("link", { name: "Troupes", exact: true }).click();
  await p.getByLabel("Troupe to join").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Visit" }).click();
  await expect(p.getByRole("listitem").filter({ hasText: troupeName })).toBeVisible();
  await p.getByRole("button", { name: "More for Agnes Moreau" }).click();
  await p.getByRole("menuitem", { name: "Rename…" }).click();
  await p.getByLabel("New name").fill("Agnes Duval");
  await p.screenshot(shots("rename"));
  await p.getByRole("button", { name: "Rename", exact: true }).click();
  await expect(p.getByRole("heading", { level: 1 })).toHaveText("Agnes Duval");
  // The menu says when the next rename is allowed instead of offering one.
  await p.getByRole("button", { name: "More for Agnes Duval" }).click();
  await expect(p.getByText(/You can rename Agnes Duval again on/)).toBeVisible();
  await expect(p.getByRole("menuitem", { name: /^Rename/ })).toBeDisabled();
  await p.screenshot(shots("rename-wait"));
  await p.keyboard.press("Escape");

  await lead.page.reload();
  await lead.page.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(lead.page.getByText("Agnes Moreau is now called Agnes Duval")).toBeVisible();

  // The custodian can still rename it, which leaves the player's wait as it was.
  const c = custodian.page;
  await c.goto(new URL(p.url()).pathname.replace(/\/troupes$/, ""));
  await rename(c, "Agnes Duval", "Agnes Lemaire");
  await p.reload();
  await p.getByRole("button", { name: "More for Agnes Lemaire" }).click();
  await expect(p.getByText(/You can rename Agnes Lemaire again on/)).toBeVisible();
  await p.keyboard.press("Escape");
  await p.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(p.getByText("The custodian renamed Agnes Duval to Agnes Lemaire")).toBeVisible();
  await p.keyboard.press("Escape");

  // The character's history keeps the old names.
  await p.locator("main").getByRole("link", { name: "Log", exact: true }).click();
  await expect(p.getByText("rename-custodian renamed Agnes Duval to Agnes Lemaire (rename-player).")).toBeVisible();
  await expect(p.getByText("rename-player renamed Agnes Moreau to Agnes Duval.")).toBeVisible();
  await p.screenshot(shots("rename-log"));
});

test("at a game, the Play View tracks blood and uses, offline too, and the storytellers reset the troupe", async ({ browser }) => {
  const custodian = await person(browser, "play-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "play-lead");
  const troupeName = `Court of Candles ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC the lead runs at game, made straight through the API: Generation 2 (12
  // blood, 2 a turn), Herd 2, Physical 5, Mental 3, Dodge 2 and Celerity 2.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Lucien", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  for (const [category, name, rating] of [
    ["clan", "Toreador", null],
    ["backgrounds", "Generation", 2],
    ["backgrounds", "Herd", 2],
    ["attributes", "Physical", 5],
    ["attributes", "Mental", 3],
    ["skills", "Dodge", 2],
    ["disciplines", "Celerity", 2],
    ["disciplines", "Potence", 2],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category, name, rating, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
  }

  // A house rule: characters start a game with 8 blood.
  await p.goto(`/troupes/${troupeId}/rules/starting`);
  await p.getByRole("button", { name: "Change starting blood" }).click();
  await p.getByLabel("This much:").check();
  await p.getByLabel("Starting blood").fill("8");
  await p.getByRole("button", { name: "Save" }).click();
  await expect(p.getByText("8 blood, or the generation's most if that is less")).toBeVisible();

  // Play, from the sheet.
  await p.goto(`/characters/${npc}/sheet`);
  await p.getByRole("link", { name: "Play", exact: true }).click();
  await expect(p.getByRole("heading", { name: "Lucien" })).toBeVisible();
  await expect(p.getByLabel("Blood: 8 of 12")).toBeVisible();
  await expect(p.getByText("2 blood a turn")).toBeVisible();
  // Quick notes start on, but Blood, Willpower and healing never stop to ask.
  await expect(p.getByLabel("Quick notes")).toBeChecked();
  await p.getByRole("button", { name: "Spend Blood", exact: true }).last().click();
  await expect(p.getByLabel("Blood: 7 of 12")).toBeVisible();
  await expect(p.getByRole("dialog", { name: "Note for this spend" })).toHaveCount(0);
  await expect(p.getByText("Blood 8 → 7")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  await p.getByLabel("Quick notes").uncheck();

  // The Pools tab, loaded once with the page: initiative with and without
  // Celerity, Dodge, and what each power does. The Sheet tab has the stats.
  await p.getByRole("tab", { name: "Pools" }).click();
  const initiative = p.getByRole("listitem").filter({ hasText: /^Initiative/ });
  await expect(initiative.getByText("5", { exact: true })).toBeVisible();
  // The pools come first; the switches are in a drawer from the button at the foot.
  const switches = p.getByRole("button", { name: "Forms, powers and modifiers" });
  await expect(switches).toHaveAccessibleDescription("Nothing in use");
  await expect(switches).toHaveAttribute("aria-expanded", "false");
  await expect(p.getByRole("heading", { name: "Forms and powers in use" })).toHaveCount(0);
  await p.evaluate(() => window.scrollTo(0, 0));
  await expect(p.locator("main section h2").first()).toBeInViewport();
  // It stays at the foot of the screen whatever the scroll, and the last panel clears it.
  await p.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await expect(switches).toBeInViewport();
  const foot = await switches.boundingBox();
  const last = await p.locator("main section").last().boundingBox();
  expect(last!.y + last!.height).toBeLessThanOrEqual(foot!.y);
  await p.evaluate(() => window.scrollTo(0, 0));
  await switches.click();
  await expect(switches).toHaveAttribute("aria-expanded", "true");
  await expect(p.getByRole("dialog", { name: "Forms, powers and modifiers" })).toBeVisible();
  // Celerity switched on: Alacrity adds its two powers to initiative, until it is off.
  await p.getByLabel("Celerity on").check();
  await expect(initiative.getByText("7", { exact: true })).toBeVisible();
  await expect(initiative).toContainText("Physical 5 + Alacrity 2");
  await expect(p.getByRole("region", { name: "Switched on now" })).toContainText("On: Celerity");
  await expect(switches).toHaveAccessibleDescription(/In use: Celerity/);
  await p.getByLabel("Celerity on").uncheck();
  await expect(switches).toHaveAccessibleDescription("Nothing in use");
  await expect(initiative.getByText("5", { exact: true })).toBeVisible();
  await expect(p.getByRole("listitem").filter({ hasText: /^Dodge/ }).getByText("7", { exact: true }).first()).toBeVisible();
  await expect(p.getByText("Alacrity", { exact: true })).toBeVisible();
  // Each attack shows what a hit does, with Potence's Might in the breakdown.
  const unarmed = p.getByRole("listitem").filter({ hasText: /^Unarmed attack/ });
  await expect(unarmed.getByText("2 damage: 1 (unarmed) + 1 (Might)")).toBeVisible();
  await expect(unarmed.getByText("An exceptional success adds 1 damage, 3 in all.")).toBeVisible();
  // The player's own modifier: Social pools go up while it is on, with Fame in the breakdown.
  const social = p.getByRole("listitem").filter({ hasText: /^Resisting Social powers/ });
  await expect(social).not.toContainText("Fame");
  await p.getByLabel("Your own modifier").fill("Fame");
  await p.getByLabel("Amount").fill("2");
  await p.getByLabel("Applies to").selectOption("Social");
  await p.getByLabel("When (a note)").fill("against mortals");
  await p.getByRole("button", { name: "Add modifier" }).click();
  await expect(social).toContainText("Fame 2");
  await expect(p.getByText("+2 Social pools, against mortals")).toBeVisible();
  await expect(switches).toHaveAccessibleDescription(/In use: \+2 Fame/);
  // Escape closes the drawer and puts focus back on the button; the button opens it again.
  await p.keyboard.press("Escape");
  await expect(p.getByRole("dialog", { name: "Forms, powers and modifiers" })).toHaveCount(0);
  await expect(switches).toBeFocused();
  await switches.click();
  // Switched off, it drops back and waits at the foot of the tab.
  await p.getByLabel("Fame on").click();
  await expect(p.getByLabel("Fame on")).not.toBeChecked();
  await expect(social).not.toContainText("Fame");
  await expect(p.getByRole("heading", { name: "Switched off" })).toBeVisible();
  await p.getByLabel("Fame on").click();
  await expect(social).toContainText("Fame 2");
  await p.screenshot(shots("play-pools"));
  await p.getByRole("tab", { name: "Sheet" }).click();
  await expect(p.getByRole("heading", { name: "Attributes" })).toBeVisible();
  await expect(p.getByRole("tab", { name: "Sheet" })).toHaveAttribute("aria-selected", "true");
  await p.screenshot(shots("play-sheet"));
  await p.getByRole("tab", { name: "Tracker" }).click();

  // No signal: the tap waits on the phone, and goes when the signal returns.
  await p.context().setOffline(true);
  await p.getByRole("button", { name: "Spend Willpower", exact: true }).last().click();
  await expect(p.getByLabel("Willpower: 5 of 6")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Offline · 1 tap waiting");
  await p.screenshot(shots("play-offline"));
  await p.context().setOffline(false);
  await expect(p.getByRole("status")).toHaveText("Saved");
  // Undo takes it back.
  await p.getByRole("button", { name: "Undo Willpower 6 → 5" }).click();
  await expect(p.getByText("Undid: Willpower 6 → 5")).toBeVisible();
  await expect(p.getByLabel("Willpower: 6 of 6")).toBeVisible();

  // Quick notes: what a Herd point was for. Then aggravated damage.
  await p.getByLabel("Quick notes").check();
  await p.getByRole("button", { name: "Use Herd" }).click();
  await p.getByLabel(/What was Herd for/).fill("fed at the club");
  await p.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(p.getByText("Herd 2 → 1")).toBeVisible();
  await expect(p.getByText("“fed at the club”")).toBeVisible();
  await p.getByLabel("Quick notes").uncheck();
  await p.getByRole("button", { name: "+ Aggravated" }).click();
  await expect(p.getByText("Health: took 1 aggravated (0 → 1 marked)")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  // The server has it all: a reload shows the same.
  await p.reload();
  await expect(p.getByLabel("Blood: 7 of 12")).toBeVisible();
  await expect(p.getByText("Backgrounds · 1 of 2 left")).toBeVisible();
  await p.screenshot(shots("play"));

  // After the game the lead resets the whole troupe, from People → At game.
  await p.goto(`/troupes/${troupeId}/play`);
  await expect(p.getByText("Blood 7/12")).toBeVisible();
  await p.getByRole("button", { name: "Reset everyone…" }).click();
  await p.getByRole("button", { name: "Reset everyone for the next game" }).click();
  await expect(p.getByText("1 character was reset.")).toBeVisible();
  await expect(p.getByText("Blood 8/12")).toBeVisible();
  await p.screenshot(shots("play-troupe"));

  // A fresh game, with the last one's log kept.
  await p.getByRole("link", { name: "Lucien" }).click();
  await expect(p.getByLabel("Blood: 8 of 12")).toBeVisible();
  await expect(p.getByText("Game 2")).toBeVisible();
  await p.getByRole("button", { name: /Game 1 ·/ }).click();
  await expect(p.getByText("“fed at the club”")).toBeVisible();

  // The modifier is still there after the Reset, and prints beside the pools it changes while it is on.
  await p.getByRole("tab", { name: "Pools" }).click();
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  await expect(p.getByLabel("Fame on")).toBeChecked();
  await p.goto(`/print/characters/${npc}`);
  await expect(p.getByText("(+2 Fame)", { exact: true })).toBeVisible();
  await expect(p.getByText("2 damage (3 exceptional)", { exact: true })).toBeVisible();
  await p.goBack();

  // With ratings as pips in Settings, the Sheet and Pools tabs show pips too:
  // Physical 5 of ten, Celerity 2, and its powers' levels.
  const asPips = await p.request.patch("/api/preferences", { headers, data: { ratings: "pips" } });
  expect(asPips.status(), await asPips.text()).toBe(200);
  await p.reload();
  await p.getByRole("tab", { name: "Sheet" }).click();
  await expect(p.getByRole("img", { name: "5 dots" }).first()).toBeVisible();
  await expect(p.getByRole("heading", { name: "Attributes" })).toBeVisible();
  await p.screenshot(shots("play-sheet-pips"));
  await p.getByRole("tab", { name: "Pools" }).click();
  await expect(p.getByText("Alacrity", { exact: true })).toBeVisible();
  await expect(p.getByRole("img", { name: "2 dots" }).first()).toBeVisible();
  await p.screenshot(shots("play-pools-pips"));
});

test("Shape of the Beast on the Play View: a Huge fight form adds Healthy levels and Brawl, flight form ends it, and the Scene shows it", async ({ browser }) => {
  const custodian = await person(browser, "beast-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "beast-lead");
  const troupeName = `Hollow Hill ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC with Shape of the Beast: Physical 5, Brawl 3, Dodge 2, Protean 4, Celerity 2.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Ursa", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  for (const [category, name, rating] of [
    ["clan", "Gangrel", null],
    ["attributes", "Physical", 5],
    ["attributes", "Mental", 3],
    ["skills", "Brawl", 3],
    ["skills", "Dodge", 2],
    ["disciplines", "Protean", 4],
    ["disciplines", "Celerity", 2],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category, name, rating, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
  }

  // On the sheet, under Protean: the fight form is a bear with the Huge template.
  await p.goto(`/characters/${npc}/sheet`);
  const choices = p.getByLabel("Shape of the Beast choices");
  await expect(choices).toContainText("flight form bat · fight form wolf · fight form template none");
  await choices.getByRole("button", { name: "choose" }).click();
  await choices.getByLabel("Fight form", { exact: true }).fill("bear");
  await choices.getByLabel("Fight form template").selectOption("Huge");
  await choices.getByRole("button", { name: "Save" }).click();
  await expect(choices).toContainText("fight form bear · fight form template Huge");

  // The Pools tab lists the forms and powers, all off.
  await p.goto(`/play/characters/${npc}?tab=pools`);
  await expect(p.getByRole("heading", { name: "Ursa" })).toBeVisible();
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  const fight = p.getByLabel("Shape of the Beast: fight form (bear, Huge) on");
  const flight = p.getByLabel("Shape of the Beast: flight form (bat) on");
  await expect(fight).not.toBeChecked();
  const unarmed = p.getByRole("listitem").filter({ hasText: /^Unarmed attack/ });
  await expect(unarmed.getByText("8", { exact: true })).toBeVisible();
  await expect(unarmed.getByText("1 damage: 1 (unarmed)")).toBeVisible();

  // Into the fight form: Brawl +2 with the reason, aggravated, and Feral Claws alongside.
  await fight.check();
  await expect(unarmed.getByText("10", { exact: true })).toBeVisible();
  await expect(unarmed).toContainText("Physical 5 + Brawl 3 + Shape of the Beast 2");
  await expect(unarmed.getByText("1 aggravated damage: 1 (unarmed), aggravated by Shape of the Beast")).toBeVisible();
  await p.getByLabel("Feral Claws on").check();
  await expect(fight).toBeChecked();
  await expect(p.getByRole("region", { name: "Switched on now" })).toContainText("In Shape of the Beast: fight form (bear, Huge)");
  await expect(p.getByRole("region", { name: "Switched on now" })).toContainText("On: Feral Claws");
  // Celerity goes with a form too.
  await p.getByLabel("Celerity on").check();
  const initiative = p.getByRole("listitem").filter({ hasText: /^Initiative/ });
  await expect(initiative).toContainText("Physical 5 + Alacrity 2");
  await p.screenshot(shots("play-forms"));

  // The health tracker has two more Healthy boxes, marked from the form; five damage reach into them.
  await p.getByRole("tab", { name: "Tracker" }).click();
  await p.getByLabel("Quick notes").uncheck();
  await expect(p.getByText("+2 Healthy from Shape of the Beast: fight form (bear, Huge)")).toBeVisible();
  await expect(p.getByLabel("unmarked, from the form")).toHaveCount(2);
  for (let i = 0; i < 5; i++) await p.getByRole("button", { name: "+ Normal" }).click();
  await expect(p.getByLabel("normal damage")).toHaveCount(5);
  await expect(p.getByLabel("normal damage, from the form")).toHaveCount(2);

  // Flight form ends the fight form: its levels go with the damage in them.
  await p.getByRole("tab", { name: "Pools" }).click();
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  await flight.check();
  await expect(fight).not.toBeChecked();
  await expect(p.getByLabel("Feral Claws on")).toBeChecked();
  await expect(unarmed.getByText("6", { exact: true })).toBeVisible();
  await expect(unarmed).toContainText("Physical (flight form) 3 + Brawl 3");
  await p.getByRole("tab", { name: "Tracker" }).click();
  await expect(p.getByLabel("normal damage")).toHaveCount(3);
  await expect(
    p.getByText("Turned into Shape of the Beast: flight form (bat): out of Shape of the Beast: fight form (bear, Huge), 2 damage in its levels gone"),
  ).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // Undo puts the fight form back, with its damage; the Scene view on another page shows it as a badge.
  await p.getByRole("button", { name: /^Undo Turned into Shape of the Beast: flight form/ }).click();
  await expect(p.getByLabel("normal damage")).toHaveCount(5);
  await expect(p.getByRole("status")).toHaveText("Saved");
  const scene = await p.context().newPage();
  await openScene(scene, troupeId, "Ursa's den");
  await scene.getByRole("combobox", { name: "Add to the scene" }).fill("Ursa");
  await scene.getByRole("option", { name: /Ursa/ }).click();
  await expect(scene.getByRole("article", { name: "Ursa" }).getByText("Shape of the Beast: fight form (bear, Huge)")).toBeVisible();
  await expect(scene.getByRole("article", { name: "Ursa" }).getByLabel("Health: 5 of 11 marked")).toBeVisible();
  await scene.close();

  // Reset for the next game turns every form and power off.
  await p.getByRole("button", { name: "Reset for next game…" }).click();
  await p.getByRole("button", { name: "Reset for next game", exact: true }).click();
  await expect(p.getByText("Game 2")).toBeVisible();
  await expect(p.getByRole("region", { name: "Switched on now" })).toHaveCount(0);
  await p.getByRole("tab", { name: "Pools" }).click();
  await p.getByRole("button", { name: "Forms, powers and modifiers" }).click();
  await expect(fight).not.toBeChecked();
  await expect(p.getByLabel("Celerity on")).not.toBeChecked();
});

test("influence spent at a game goes in the troupe's influence log, and comes off the next downtime", async ({ browser }) => {
  // A whole character creation, a home troupe, then a game and a downtime.
  test.slow();
  const custodian = await person(browser, "game-infl-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "game-infl-lead");
  const player = await person(browser, "game-infl-player");
  const troupeName = `Court of Whispers ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };

  // Iris, built for the troupe with Elite 3, takes a News Media specialisation and makes it her home.
  const p = player.page;
  await p.reload();
  await p.getByLabel("Name").fill("Iris");
  await p.getByLabel("Build for").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Create" }).click();
  await p.getByLabel("Clan").selectOption("Brujah");
  await expect(p.getByLabel("Clan")).toHaveValue("Brujah");
  await p.getByLabel("Sect").selectOption("Camarilla");
  const next = async (heading: string) => {
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
  };
  const tap = async (...dots: string[]) => {
    for (const dot of dots) await p.getByRole("button", { name: dot, exact: true }).click();
  };
  await next("Attributes");
  await tap("Physical 7", "Social 5", "Mental 3");
  await next("Focuses");
  await tap("Strength 1", "Wits 1", "Charisma 1");
  await next("Skills");
  await tap("Brawl 4", "Dodge 3", "Athletics 3", "Awareness 2", "Empathy 2", "Firearms 2");
  await tap("Investigation 1", "Leadership 1", "Medicine 1", "Melee 1");
  await next("Backgrounds");
  await tap("Influences: The Elite 3", "Herd 2", "Generation 1");
  await next("Disciplines");
  await tap("Celerity 2", "Potence 1", "Presence 1");
  await next("Merits & flaws");
  await next("Review");
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  const iris = new URL(p.url()).pathname.split("/")[2]!;
  const special = await p.request.put(`/api/characters/${iris}/traits`, {
    headers,
    data: { category: "influence_elite_specializations", name: "News Media", rating: 1 },
  });
  expect(special.status(), await special.text()).toBe(200);
  await p.locator("main").getByRole("link", { name: "Troupes", exact: true }).click();
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(/Waiting for .* storytellers/)).toBeVisible();
  const queue = await l.request.get(`/api/troupes/${troupeId}/approvals`, { headers });
  for (const request of await queue.json()) {
    const approved = await l.request.post(`/api/approvals/${request.id}/approve`, { headers, data: {} });
    expect(approved.status(), await approved.text()).toBe(200);
  }

  // At the game: spending Elite always asks what it was for, offering only the actions Iris can reach.
  await p.goto(`/play/characters/${iris}`);
  const elite = p.getByRole("listitem").filter({ hasText: "Influences: The Elite" });
  await expect(elite.getByText("Backgrounds · 3 of 3 left")).toBeVisible();
  await expect(elite.getByRole("button", { name: /^Restore/ })).toHaveCount(0);
  await p.getByRole("button", { name: "Use Influences: The Elite" }).click();
  const sheet = p.getByRole("dialog", { name: "Spend Elite influence" });
  await expect(sheet.getByLabel("Action").getByRole("option", { name: "5: No Party Crashers" })).toHaveCount(0);
  await sheet.getByLabel("Specialisation").selectOption("News Media");
  await expect(sheet.getByText("Your News Media specialisation counts your Elite as 4 for this.")).toHaveCount(0);
  await sheet.getByLabel("Action").selectOption({ label: "4: Smooth Over" });
  await expect(sheet.getByText("Your News Media specialisation counts your Elite as 4 for this.")).toBeVisible();
  await sheet.getByLabel("Action").selectOption({ label: "2: Gossip and Insider Trading" });
  await sheet.getByLabel("Purpose").fill("To hear what is said about the mayor");
  await p.screenshot(shots("play-influence"));
  await sheet.getByRole("button", { name: "Spend", exact: true }).click();
  await expect(p.getByText("Elite: 2: Gossip and Insider Trading (News Media), To hear what is said about the mayor")).toBeVisible();
  await expect(elite.getByText("Backgrounds · 2 of 3 left")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // A loud room: Skip details spends it all the same.
  await p.getByRole("button", { name: "Use Influences: The Elite" }).click();
  await sheet.getByRole("button", { name: "Skip details" }).click();
  await expect(p.getByText("Elite: details to come")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // One spent by mistake, and undone.
  await p.getByRole("button", { name: "Use Influences: The Elite" }).click();
  await sheet.getByRole("button", { name: "Skip details" }).click();
  await expect(elite.getByText("Backgrounds · 0 of 3 left")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await p.getByRole("button", { name: "Undo Elite: details to come" }).click();
  await expect(p.getByText("Undid: Influences: The Elite 1 → 0")).toBeVisible();
  await expect(elite.getByText("Backgrounds · 1 of 3 left")).toBeVisible();

  // The troupe's influence log has the two spends, one needing details, and not the one undone.
  await l.goto(`/troupes/${troupeId}/influence`);
  const e1 = l.getByRole("listitem", { name: "Entry E1" });
  await expect(e1.getByText("To hear what is said about the mayor")).toBeVisible();
  await expect(e1.getByText("At a game")).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E2" }).getByText("needs details")).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Entry E3" })).toHaveCount(0);

  // Iris adds the details from the game's log, while the game goes on.
  await p.getByRole("button", { name: "Add details to E2" }).click();
  const later = p.getByRole("dialog", { name: "Details of E2" });
  await later.getByLabel("Action").selectOption({ label: "1: A Friend in Need" });
  await later.getByLabel("Purpose").fill("To get a favour from the mayor's aide");
  await later.getByRole("button", { name: "Save details" }).click();
  await expect(p.getByText("Elite: 1: A Friend in Need, To get a favour from the mayor's aide")).toBeVisible();
  await l.reload();
  await expect(l.getByRole("listitem", { name: "Entry E2" }).getByText("To get a favour from the mayor's aide")).toBeVisible();

  // One pool a month: the next downtime's Elite allowance is two lower, for the two spent at the game.
  const now = Date.now();
  const made = await l.request.post(`/api/troupes/${troupeId}/cycles`, {
    headers,
    data: { name: "After the game", closes_at: new Date(now + 7 * 86400e3).toISOString(), grace_ends_at: new Date(now + 9 * 86400e3).toISOString() },
  });
  expect(made.status(), await made.text()).toBe(201);
  const cycleId = (await made.json()).id;
  const opened = await l.request.post(`/api/cycles/${cycleId}/open`, { headers });
  expect(opened.status(), await opened.text()).toBe(200);
  await l.goto(`/cycles/${cycleId}/participants`);
  await expect(l.getByText(/1 influence elite/)).toBeVisible();
  await expect(l.getByText(/^-1 influence_elite: Spent at the \d+ \w+ game$/)).toHaveCount(2);
  await l.screenshot(shots("cycle-influence-owed"));
});

test("anyone can read About, with the Dark Pack Agreement's notices", async ({ browser }) => {
  // Signed out: the sign-in page's footer links to it.
  const page = await (await browser.newContext()).newPage();
  await page.goto("/sign-in");
  await expect(page.getByText(/Unofficial fan-made material under Paradox Interactive's Dark Pack Agreement/)).toBeVisible();
  await page.getByRole("link", { name: "About Horatio" }).click();
  await expect(page.getByRole("heading", { name: "About Horatio" })).toBeVisible();
  await expect(page.getByText(/Portions of the materials are the copyrights and trademarks of Paradox Interactive AB, and are used with permission/)).toBeVisible();
  await expect(page.getByText(/not official World of Darkness material/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Dark Pack Agreement" })).toBeVisible();
  await page.screenshot(shots("about"));
});

test("settings are kept on the account, and the dark is not optional", async ({ browser }) => {
  const { page } = await person(browser, "settings-player");
  await page.getByRole("link", { name: "settings-player" }).click();
  await page.locator("main").getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByRole("radiogroup", { name: "Show ratings as" }).getByRole("radio", { name: "Pips" }).click();
  await expect(page.getByRole("radiogroup", { name: "Show ratings as" }).getByRole("radio", { name: "Pips" })).toHaveAttribute("aria-checked", "true");
  // While a change is saving, the other settings wait for it, so none is lost.
  await page.route("**/api/preferences", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    await route.continue();
  });
  await page.getByRole("radiogroup", { name: "Paper" }).getByRole("radio", { name: "A4" }).click();
  const clock24 = page.getByRole("radiogroup", { name: "Clock" }).getByRole("radio", { name: "21:30" });
  await expect(clock24).toBeDisabled();
  await expect(page.getByText("Saving…")).toBeVisible();
  await expect(clock24).toBeEnabled();
  await page.unroute("**/api/preferences");
  const saved = page.waitForResponse("**/api/preferences");
  await clock24.click();
  await saved;
  // Saved on the account: all three are still set after a reload.
  await page.reload();
  await expect(page.getByRole("radiogroup", { name: "Show ratings as" }).getByRole("radio", { name: "Pips" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("radiogroup", { name: "Paper" }).getByRole("radio", { name: "A4" })).toHaveAttribute("aria-checked", "true");
  await expect(clock24).toHaveAttribute("aria-checked", "true");
  const mode = page.getByRole("radiogroup", { name: "Light mode or dark mode" });
  await expect(mode.getByRole("radio", { name: "Light" })).toBeDisabled();
  await expect(mode.getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText("The World of Darkness is always dark.")).toBeVisible();
  await page.screenshot(shots("settings"));
});

test("notifications by email: a choice per kind, once the server can send email", async ({ browser }) => {
  const { page } = await person(browser, "email-player");
  await page.goto("/account/settings");
  // This suite's server has no email set up, and the setting says so.
  await expect(page.getByText("Email isn't set up on this server, so notifications come only to the bell.")).toBeVisible();
  await expect(page.getByRole("radiogroup", { name: "Downtime results" })).toHaveCount(0);

  // Where it is set up, each kind is bell only until chosen, and the choice is kept.
  await page.route("**/api/preferences/email", (route) => route.fulfill({ json: { available: true } }));
  await page.reload();
  const downtime = page.getByRole("radiogroup", { name: "Downtime results" });
  await expect(downtime.getByRole("radio", { name: "Bell only" })).toHaveAttribute("aria-checked", "true");
  await downtime.getByRole("radio", { name: "Bell and email" }).click();
  await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.ok()),
    page.getByRole("radiogroup", { name: "Send emails" }).getByRole("radio", { name: "Once a day" }).click(),
  ]);
  await expect(page.getByText(/gathers them into one email at 8 am/)).toBeVisible();
  await page.reload();
  await expect(downtime.getByRole("radio", { name: "Bell and email" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("radiogroup", { name: "Send emails" }).getByRole("radio", { name: "Once a day" })).toHaveAttribute("aria-checked", "true");
  await page.screenshot(shots("settings-email"));

  // An unsubscribe link that isn't real says so, and where to choose instead.
  await page.goto("/unsubscribe/not-a-real-link");
  await expect(page.getByText(/This unsubscribe link doesn't work/)).toBeVisible();
});

test("a handle to be found by, and to sign in with", async ({ browser }) => {
  const { page } = await person(browser, "handle-player");
  await page.getByRole("link", { name: "handle-player" }).click();
  await page.locator("main").getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByLabel("Your handle")).toHaveValue(`handle-player_${run.slice(-10)}`);
  const handle = `Owl_${run.slice(-10)}`;
  await page.getByLabel("Your handle").fill(handle);
  await page.getByRole("button", { name: "Change handle" }).click();
  await expect(page.getByText(`Your handle is now @${handle}.`)).toBeVisible();
  await expect(page.getByText(/^You can change it again on /)).toBeVisible();
  await page.screenshot(shots("settings-handle"));

  // Signing in with it, in any case, from another browser.
  const other = await (await browser.newContext()).newPage();
  await other.goto("/sign-in");
  await other.getByLabel("Email or handle").fill(handle.toLowerCase());
  await other.getByLabel("Password").fill(PASSWORD);
  await other.getByRole("button", { name: "Sign in" }).click();
  await expect(other.getByRole("heading", { name: "Your characters" })).toBeVisible();
});

test("a lead adds staff by picking from a list of people, the troupe's own players first", async ({ browser }) => {
  const custodian = await person(browser, "staff-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "staff-lead");
  const player = await person(browser, "staff-player");
  const troupeName = `Court of Keys ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  // The custodian finds the lead in the list by typing part of their handle.
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle.slice(0, -2));
  await custodian.page.getByRole("listbox", { name: "People" }).getByRole("option", { name: `@${lead.handle}` }).click();
  await expect(custodian.page.getByLabel("Lead storyteller")).toHaveValue(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // The player's character visits the troupe.
  const p = player.page;
  await p.getByLabel("Name").fill("Agnes Moreau");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  await p.locator("main").getByRole("link", { name: "Troupes", exact: true }).click();
  await p.getByLabel("Troupe to join").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Visit" }).click();
  await expect(p.getByRole("listitem").filter({ hasText: troupeName })).toBeVisible();
  // Home troupe comes first, then the visiting troupes, each with what it means.
  await expect(p.locator("main section h2")).toHaveText(["Home troupe", "Visiting troupes"]);
  const card = (title: string) => p.locator("main section").filter({ has: p.getByRole("heading", { name: title }) });
  await expect(card("Home troupe").getByText("The one troupe that holds this character's sheet.")).toBeVisible();
  await expect(card("Visiting troupes").getByText("A troupe this character plays in without its home there.")).toBeVisible();

  // The list opens as soon as the box is clicked: the troupe's player first.
  await lead.page.getByRole("link", { name: "Troupes" }).click();
  await lead.page.getByRole("link", { name: troupeName }).click();
  await lead.page.getByRole("link", { name: "Staff", exact: true }).click();
  await lead.page.getByLabel("Person").click();
  const people = lead.page.getByRole("listbox", { name: "People" });
  await expect(people.getByRole("option").first()).toContainText(`@${player.handle}`);
  await expect(people.getByRole("option").first()).toContainText("Plays here");
  await expect(people).not.toContainText("@example.com");
  await lead.page.screenshot(shots("staff-picker"));
  await people.getByRole("option", { name: `@${player.handle}` }).click();
  await expect(lead.page.getByLabel("Person")).toHaveValue(player.handle);
  await lead.page.getByRole("button", { name: "Save" }).click();
  await expect(lead.page.getByText(`@${player.handle} · Narrator`)).toBeVisible();

  // Now on the staff, they are greyed out with their role.
  await lead.page.getByLabel("Person").click();
  const added = people.getByRole("option", { name: `@${player.handle}` });
  await expect(added).toHaveAttribute("aria-disabled", "true");
  await expect(added).toContainText("Narrator");
  // So is the lead.
  await lead.page.getByLabel("Person").fill(lead.handle);
  await expect(people.getByRole("option", { name: `@${lead.handle}` })).toHaveAttribute("aria-disabled", "true");
  await expect(people.getByRole("option", { name: `@${lead.handle}` })).toContainText("Lead Storyteller");
  await lead.page.keyboard.press("Escape");

  // Their role is changed in the staff list.
  await lead.page.getByLabel("Role for staff-player").selectOption("assistant_storyteller");
  await expect(lead.page.getByText(`@${player.handle} · Assistant Storyteller`)).toBeVisible();
});

test("dates and times show in each person's zone and format", async ({ browser }) => {
  const { page } = await person(browser, "dates-player");
  // A rename puts a line in the character's log, on the default 12-hour clock in this device's zone.
  await page.goto("/characters");
  await page.getByLabel("Name").fill("Odile Marchand");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  await page.getByRole("button", { name: "More for Odile Marchand" }).click();
  await page.getByRole("menuitem", { name: "Rename…" }).click();
  await page.getByLabel("New name").fill("Odile Brun");
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Odile Brun");
  await page.locator("main").getByRole("link", { name: "Log", exact: true }).click();
  const renamed = page.locator("main time").first();
  await expect(renamed).toHaveText(/^\d{1,2} [A-Z][a-z]{2} \d{4}, \d{1,2}:\d{2} [ap]m$/);
  const log = page.url();

  // In Tokyo, as ISO dates on a 24-hour clock: the page says at once how a deadline will show.
  // Each change is waited for, to be sure it is saved before the next page.
  const saved = () => page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.request().method() === "PATCH" && r.ok());
  await page.goto("/account/settings");
  await Promise.all([saved(), page.getByLabel("Time zone").fill("Asia/Tokyo")]);
  await Promise.all([saved(), page.getByRole("radiogroup", { name: "Dates" }).getByRole("radio", { name: "2026-10-20" }).click()]);
  await Promise.all([saved(), page.getByRole("radiogroup", { name: "Clock" }).getByRole("radio", { name: "21:30" }).click()]);
  await expect(page.getByText(/^[A-Z][a-z]{2} \d{4}-\d{2}-\d{2}, \d{2}:\d{2} GMT\+9$/)).toBeVisible();
  await page.screenshot(shots("settings-dates"));
  await page.goto(log);
  const at = new Date((await renamed.getAttribute("datetime")) ?? "");
  const part = (type: string, parts: Intl.DateTimeFormatPart[]) => parts.find((p) => p.type === type)?.value;
  const tokyo = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(at);
  await expect(renamed).toHaveText(`${part("year", tokyo)}-${part("month", tokyo)}-${part("day", tokyo)}, ${part("hour", tokyo)}:${part("minute", tokyo)}`);
  await page.screenshot(shots("log-dates"));

  // Back to this device's zone: the zone is cleared, and kept that way after a reload.
  await page.goto("/account/settings");
  await Promise.all([saved(), page.getByRole("button", { name: "Use this device's" }).click()]);
  await expect(page.getByLabel("Time zone")).toHaveValue("");
  await page.reload();
  await expect(page.getByLabel("Time zone")).toHaveValue("");
  await expect(page.getByText(/^[A-Z][a-z]{2} \d{4}-\d{2}-\d{2}, \d{2}:\d{2} \S+$/)).toBeVisible();
});

test("large text makes the app bigger, but not printed sheets and badges", async ({ browser }) => {
  const { page } = await person(browser, "large-text");
  await page.getByLabel("Name").fill("Squint");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  const character = new URL(page.url()).pathname.split("/")[2]!;
  const fontSize = () => page.evaluate(() => getComputedStyle(document.documentElement).fontSize);
  const normal = await fontSize();

  await page.getByRole("link", { name: "large-text" }).click();
  await page.locator("main").getByRole("link", { name: "Settings", exact: true }).click();
  const saved = page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.ok());
  await page.getByRole("radiogroup", { name: "Text size" }).getByRole("radio", { name: "Large" }).click();
  // At once, with no reload, and still after one (once it has saved).
  await expect.poll(fontSize).not.toBe(normal);
  const large = await fontSize();
  expect(parseFloat(large) / parseFloat(normal)).toBeCloseTo(1.15);
  await saved;
  await page.reload();
  await expect(page.getByRole("radiogroup", { name: "Text size" }).getByRole("radio", { name: "Large" })).toHaveAttribute("aria-checked", "true");
  await expect.poll(fontSize).toBe(large);
  await page.screenshot(shots("settings-large-text"));

  // The Play View too.
  await page.goto(`/play/characters/${character}`);
  await expect(page.getByText("Squint").first()).toBeVisible();
  await expect.poll(fontSize).toBe(large);
  // But the printed sheet and badge keep their own sizes.
  await page.goto(`/print/characters/${character}`);
  await expect(page.getByText("Squint").first()).toBeVisible();
  expect(await fontSize()).toBe(normal);
  await page.goto(`/print/characters/${character}/badge`);
  await expect(page.getByText("Squint").first()).toBeVisible();
  expect(await fontSize()).toBe(normal);

  // And back to normal.
  await page.goto("/account/settings");
  await expect.poll(fontSize).toBe(large);
  await page.getByRole("radiogroup", { name: "Text size" }).getByRole("radio", { name: "Normal" }).click();
  await expect.poll(fontSize).toBe(normal);
});

test("the Play View opens as the settings say", async ({ browser }) => {
  const { page } = await person(browser, "play-settings-player");
  // Headless browsers may refuse a wake lock, so this one is a stand-in that grants it.
  await page.context().addInitScript(() => {
    class Lock extends EventTarget {
      released = false;
      async release() {
        this.released = true;
        this.dispatchEvent(new Event("release"));
      }
    }
    Object.defineProperty(navigator, "wakeLock", { value: { request: async () => new Lock() }, configurable: true });
  });
  await page.getByLabel("Name").fill("Mireille");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  const characterId = new URL(page.url()).pathname.split("/")[2]!;

  // As it opens by default: on the Tracker, quick notes on, the screen left to dim.
  await page.goto(`/play/characters/${characterId}`);
  await expect(page.getByRole("tab", { name: "Tracker" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Quick notes")).toBeChecked();
  await expect(page.getByText("Screen awake")).toHaveCount(0);

  // Quick notes off, the screen kept awake, opening on Pools.
  await page.goto("/account/settings");
  const saved = () => page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.ok());
  for (const label of ["Quick notes", "Keep the screen awake"]) {
    const done = saved();
    await page.getByLabel(label).click();
    await done;
  }
  await expect(page.getByLabel("Quick notes")).not.toBeChecked();
  await expect(page.getByLabel("Keep the screen awake")).toBeChecked();
  const done = saved();
  await page.getByRole("radiogroup", { name: "The Play View opens on" }).getByRole("radio", { name: "Pools" }).click();
  await done;

  await page.goto(`/play/characters/${characterId}`);
  await expect(page.getByRole("tab", { name: "Pools" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("Screen awake")).toBeVisible();
  await page.screenshot(shots("play-settings"));
  // Choosing the Tracker stays on it, and a spend asks for no note.
  await page.getByRole("tab", { name: "Tracker" }).click();
  await expect(page.getByRole("tab", { name: "Tracker" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Quick notes")).not.toBeChecked();
  await page.getByRole("button", { name: "Spend Willpower", exact: true }).last().click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

/**
 * Stand-ins for what feeding's finish uses, so a test can see it happen: the
 * sound (oscillators made), a vibration and a notification, granted.
 */
async function watchFeeding(page: Page) {
  await page.context().addInitScript(() => {
    const seen = { sounds: 0, buzzes: 0, notes: [] as string[] };
    (window as unknown as { seen: typeof seen }).seen = seen;
    const Audio = window.AudioContext;
    if (Audio) {
      const make = Audio.prototype.createOscillator;
      Audio.prototype.createOscillator = function () {
        seen.sounds++;
        return make.call(this);
      };
    }
    Object.defineProperty(navigator, "vibrate", { value: () => ((seen.buzzes++), true), configurable: true });
    class Note {
      static permission = "granted";
      static requestPermission = async () => "granted";
      constructor(title: string) {
        seen.notes.push(title);
      }
    }
    Object.defineProperty(window, "Notification", { value: Note, configurable: true, writable: true });
  });
}

const seen = (page: Page) => page.evaluate(() => (window as unknown as { seen: { sounds: number; buzzes: number; notes: string[] } }).seen);

/** Hide or show the page, as locking the phone or switching apps does. */
async function setShown(page: Page, shown: boolean) {
  await page.evaluate((shown) => {
    Object.defineProperty(document, "visibilityState", { value: shown ? "visible" : "hidden", configurable: true });
    Object.defineProperty(document, "hidden", { value: !shown, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  }, shown);
}

test("Feed on the Play View: 15 minutes for 2 Blood, kept through a reload, cancelled, and capped at the most", async ({ browser }) => {
  const { page } = await person(browser, "feed-player");
  await watchFeeding(page);
  await page.clock.install();
  await page.getByLabel("Name").fill("Ottilie");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Concept" })).toBeVisible();
  const characterId = new URL(page.url()).pathname.split("/")[2]!;

  // No Herd: 10 Blood, 3 spent.
  await page.goto(`/play/characters/${characterId}`);
  await page.getByLabel("Quick notes").uncheck();
  for (let i = 0; i < 3; i++) await page.getByRole("button", { name: "Spend Blood", exact: true }).last().click();
  await expect(page.getByLabel("Blood: 7 of 10")).toBeVisible();

  // The sheet says what will happen; its Cancel changes nothing.
  await page.getByRole("button", { name: "Feed", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Feed" });
  await expect(sheet).toContainText("Feed — 15 minutes, +2 Blood.");
  await expect(sheet).toContainText("+2 Blood: Blood 7 → 9");
  await expect(sheet).toContainText("Tell a storyteller or narrator you're feeding first.");
  await expect(sheet).toContainText("core p. 294");
  await expect(sheet.getByRole("radio")).toHaveCount(0);
  await page.screenshot(shots("feed-sheet"));
  await sheet.getByRole("button", { name: "Cancel" }).click();
  await expect(sheet).toHaveCount(0);

  // Started, it counts down, and a reload keeps the time.
  await page.getByRole("button", { name: "Feed", exact: true }).click();
  await sheet.getByRole("button", { name: "Start" }).click();
  const timer = page.getByRole("dialog", { name: "Feeding" });
  await expect(timer.getByRole("timer")).toHaveText(/^(15:00|14:5\d)$/);
  await page.clock.fastForward("05:00");
  await expect(timer.getByRole("timer")).toHaveText(/^(10:00|09:5\d)$/);
  await page.reload();
  await expect(timer.getByRole("timer")).toHaveText(/^(10:00|09:5\d)$/);
  await page.screenshot(shots("feed-timer"));

  // Cancel stops it and changes nothing, even after a reload.
  await timer.getByRole("button", { name: "Cancel" }).click();
  await expect(timer).toHaveCount(0);
  await expect(page.getByLabel("Blood: 7 of 10")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Blood: 7 of 10")).toBeVisible();
  await expect(timer).toHaveCount(0);
  await expect(page.getByText("“Fed”")).toHaveCount(0);

  // The whole 15 minutes: blood rises, a sound and a buzz, and +2 Blood.
  await page.getByRole("button", { name: "Feed", exact: true }).click();
  await sheet.getByRole("button", { name: "Start" }).click();
  await page.clock.fastForward("15:00");
  const fed = page.getByRole("dialog", { name: "You fed" });
  await expect(fed).toContainText("You fed.+2 Blood (hunted): Blood 7 → 9.");
  await expect(fed.getByTestId("feed-fill")).toHaveAttribute("data-motion", "fill");
  expect((await seen(page)).sounds).toBeGreaterThan(0);
  expect((await seen(page)).buzzes).toBe(1);
  await page.waitForTimeout(2000);
  await page.screenshot(shots("feed-done"));
  await fed.getByRole("button", { name: "Done" }).click();
  await expect(fed).toHaveCount(0);
  await expect(page.getByLabel("Blood: 9 of 10")).toBeVisible();
  await expect(page.getByText("Blood 7 → 9")).toBeVisible();
  await expect(page.getByText("“Fed (hunted)”")).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Saved");

  // Turned off on the timer, the sound stays off. Blood can't go above the most.
  await page.getByRole("button", { name: "Feed", exact: true }).click();
  await sheet.getByRole("button", { name: "Start" }).click();
  await timer.getByLabel("Sound").uncheck();
  await page.reload();
  await expect(timer.getByLabel("Sound")).not.toBeChecked();
  await page.clock.fastForward("15:00");
  await expect(fed).toContainText("+1 Blood (hunted), now full: Blood 9 → 10.");
  expect((await seen(page)).sounds).toBe(0); // a fresh page since the reload, and no sound made
  await fed.getByRole("button", { name: "Done" }).click();
  await expect(page.getByLabel("Blood: 10 of 10")).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Saved");
});

test("Feed with Herd: 5 minutes for Blood equal to Herd, waiting while the phone is locked, added once, with Undo", async ({ browser }) => {
  const custodian = await person(browser, "feed-custodian");
  makeCustodian(custodian.email);
  // Reduced motion: the finish fades in rather than filling the screen.
  const lead = await person(browser, "feed-lead", { reducedMotion: "reduce" });
  const troupeName = `Court of Thirst ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC with Herd 3, played by the lead: staff start Feed for a character too.
  const p = lead.page;
  await watchFeeding(p);
  await p.clock.install();
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Benedek", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category: "backgrounds", name: "Herd", rating: 3, detail: "" } });
  expect(rated.status(), await rated.text()).toBe(200);

  await p.goto(`/play/characters/${npc}`);
  await p.getByLabel("Quick notes").uncheck();
  for (let i = 0; i < 4; i++) await p.getByRole("button", { name: "Spend Blood", exact: true }).last().click();
  await expect(p.getByLabel("Blood: 6 of 10")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  await p.getByRole("button", { name: "Feed", exact: true }).click();
  const sheet = p.getByRole("dialog", { name: "Feed" });
  // Both feeds are offered, the Herd one chosen to start with, each saying what it gives.
  await expect(sheet.getByRole("radio")).toHaveCount(2);
  await expect(sheet.getByRole("radio", { name: /Feed from your Herd: 5 minutes, \+3 Blood \(Herd 3\)/ })).toBeChecked();
  await expect(sheet.getByRole("radio", { name: /Hunt: 15 minutes, \+2 Blood/ })).not.toBeChecked();
  await expect(sheet).toContainText("+3 Blood: Blood 6 → 9");
  await expect(sheet).toContainText("+2 Blood: Blood 6 → 8");
  await expect(sheet).toContainText("Your Herd is quicker and gives more");
  await expect(sheet).toContainText("core pp. 102–103");
  await sheet.getByRole("button", { name: "Start" }).click();
  const timer = p.getByRole("dialog", { name: "Feeding" });
  await expect(timer.getByRole("timer")).toHaveText(/^(05:00|04:5\d)$/);

  // The phone locked for two minutes: the time is still right when it is back.
  await setShown(p, false);
  await p.clock.fastForward("02:00");
  await setShown(p, true);
  await expect(timer.getByRole("timer")).toHaveText(/^(03:00|02:5\d)$/);

  // Locked when the time is up: a notification, and the Blood waits.
  await setShown(p, false);
  await p.clock.fastForward("03:00");
  await expect.poll(async () => (await seen(p)).notes).toEqual(["Feeding is done"]);
  await expect(timer.getByRole("timer")).toHaveText("00:00");
  const fed = p.getByRole("dialog", { name: "You fed" });
  await expect(fed).toHaveCount(0);
  const blood = async () => (await (await p.request.get(`/api/characters/${npc}/play`)).json()).blood.value;
  expect(await blood()).toBe(6);

  // Back to the page: the result, faded in, and the Blood added.
  await setShown(p, true);
  await expect(fed).toContainText("You fed.+3 Blood (Herd 3): Blood 6 → 9.");
  await expect(fed.getByTestId("feed-fill")).toHaveAttribute("data-motion", "fade");
  await p.screenshot(shots("feed-done-reduced-motion"));
  // Never twice: a reload shows the same result, and other devices see it once.
  await expect.poll(blood).toBe(9);
  await p.reload();
  await expect(fed).toContainText("+3 Blood (Herd 3): Blood 6 → 9.");
  await p.waitForTimeout(500);
  expect(await blood()).toBe(9);
  const log = (await (await p.request.get(`/api/characters/${npc}/play`)).json()).log as { note: string }[];
  expect(log.filter((e) => e.note === "Fed (Herd 3)")).toHaveLength(1);

  // Undo takes it back, as any tap.
  await fed.getByRole("button", { name: "Undo" }).click();
  await expect(fed).toHaveCount(0);
  await expect(p.getByLabel("Blood: 6 of 10")).toBeVisible();
  await expect(p.getByText("Undid: Blood 6 → 9")).toBeVisible();
  await expect.poll(blood).toBe(6);

  // With Herd 1 the hunt is chosen to start with, and taking it gives +2 after 15 minutes.
  const lowered = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category: "backgrounds", name: "Herd", rating: 1, detail: "" } });
  expect(lowered.status(), await lowered.text()).toBe(200);
  await p.reload();
  await p.getByRole("button", { name: "Feed", exact: true }).click();
  await expect(sheet.getByRole("radio", { name: /Hunt: 15 minutes, \+2 Blood/ })).toBeChecked();
  await expect(sheet.getByRole("radio", { name: /Feed from your Herd: 5 minutes, \+1 Blood \(Herd 1\)/ })).not.toBeChecked();
  await expect(sheet).toContainText("Your Herd is quicker, but hunting gives more Blood");
  await sheet.getByRole("button", { name: "Start" }).click();
  await expect(timer.getByRole("timer")).toHaveText(/^(15:00|14:5\d)$/);
  await expect(timer).toContainText("Hunting");
  await p.clock.fastForward("15:00");
  await expect(fed).toContainText("You fed.+2 Blood (hunted): Blood 6 → 8.");
  await expect.poll(blood).toBe(8);
  const hunted = (await (await p.request.get(`/api/characters/${npc}/play`)).json()).log as { note: string }[];
  expect(hunted.filter((e) => e.note === "Fed (hunted)")).toHaveLength(1);
});

/** A new scene in the troupe, made through the API, opened on the page. */
async function openScene(page: Page, troupeId: string, name: string): Promise<string> {
  const made = await page.request.post(`/api/troupes/${troupeId}/scenes`, { headers: { "X-Horatio": "1" }, data: { name } });
  expect(made.status(), await made.text()).toBe(201);
  const sceneId: string = (await made.json()).id;
  await page.goto(`/play/troupes/${troupeId}/scenes/${sceneId}`);
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  return sceneId;
}

test("a storyteller pins three NPCs in a Scene view, taps for two, and each full Play View agrees", async ({ browser }) => {
  const custodian = await person(browser, "scene-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "scene-lead");
  const troupeName = `Court of Masks ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Three NPCs, made straight through the API.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const npcs: Record<string, string> = {};
  for (const name of ["Alder", "Brant", "Cassia"]) {
    const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(made.status(), await made.text()).toBe(201);
    npcs[name] = (await made.json()).id;
  }
  const state = async (name: string) => (await p.request.get(`/api/characters/${npcs[name]}/play`)).json();

  // From the At game tab, through the troupe's scenes, to a new empty one.
  await p.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await p.getByRole("link", { name: "At game" }).click();
  await p.getByRole("link", { name: "Open the scenes" }).click();
  await expect(p.getByRole("heading", { name: "Scenes", exact: true })).toBeVisible();
  await p.getByLabel("Name of a new scene").fill("Masked ball");
  await p.getByRole("button", { name: "New scene" }).click();
  await expect(p.getByRole("heading", { name: "Masked ball", exact: true })).toBeVisible();
  await expect(p.getByText("Nobody is in the scene yet.")).toBeVisible();
  const sceneUrl = new URL(p.url()).pathname;
  const pinned = async () => (await (await p.request.get(`/api/troupes/${troupeId}/scenes/${sceneUrl.split("/").pop()}`)).json()).characters.length;

  // Pinned by searching: typing narrows the list, and a pinned one is not offered again.
  const search = p.getByRole("combobox", { name: "Add to the scene" });
  await search.fill("al");
  await expect(p.getByRole("option")).toHaveCount(1);
  await p.getByRole("option", { name: /Alder/ }).click();
  await search.fill("bra");
  await p.getByRole("option", { name: /Brant/ }).click();
  await search.click();
  await expect(p.getByRole("option", { name: /Alder/ })).toHaveCount(0);
  await p.getByRole("option", { name: /Cassia/ }).click();
  const card = (name: string) => p.getByRole("article", { name });
  await expect(p.getByRole("article")).toHaveCount(3);
  await expect(card("Cassia").getByLabel("Blood: 10 of 10")).toBeVisible();

  // The scene is kept on the server.
  await expect.poll(pinned).toBe(3);
  await p.reload();
  await expect(p.getByRole("article")).toHaveCount(3);
  await expect(card("Brant")).toBeVisible();

  // Taps for two of them: Blood and Health.
  const alder = card("Alder");
  await alder.getByRole("button", { name: "Spend Blood", exact: true }).click();
  await alder.getByRole("button", { name: "Spend Blood", exact: true }).click();
  await alder.getByRole("button", { name: "+ Normal" }).click();
  await expect(alder.getByLabel("Blood: 8 of 10")).toBeVisible();
  await expect(alder.getByLabel(/^Health: 1 of \d+ marked$/)).toBeVisible();
  const brant = card("Brant");
  await brant.getByRole("button", { name: "Spend Blood", exact: true }).click();
  await brant.getByRole("button", { name: "+ Aggravated" }).click();
  await expect(brant.getByLabel("Blood: 9 of 10")).toBeVisible();
  await expect(alder.getByRole("status")).toHaveText("Saved");
  await expect(brant.getByRole("status")).toHaveText("Saved");
  await expect(card("Cassia").getByLabel("Blood: 10 of 10")).toBeVisible();
  await p.screenshot(shots("scene"));

  // The server has the taps, and the full Play View of each shows the same.
  await expect.poll(async () => (await state("Alder")).blood.value).toBe(8);
  expect((await state("Alder")).health.marks).toEqual(["normal"]);
  expect((await state("Brant")).health.marks).toEqual(["aggravated"]);
  expect((await state("Cassia")).log).toHaveLength(0);
  await alder.getByRole("link", { name: "Open the full Play View of Alder" }).click();
  await expect(p.getByLabel("Blood: 8 of 10")).toBeVisible();
  await expect(p.getByLabel("normal damage")).toHaveCount(1);
  await expect(p.getByText("Blood 10 → 9")).toBeVisible();
  // Opened from the scene, the way back is to the scene, whichever tab is looked up.
  await expect(p.getByRole("link", { name: "← Alder" })).toHaveCount(0);
  await p.getByRole("tab", { name: "Sheet" }).click();
  await p.getByRole("link", { name: "← Back to the scene" }).click();
  await expect(p.getByRole("heading", { name: "Masked ball", exact: true })).toBeVisible();
  await expect(p.getByRole("article")).toHaveCount(3);
  await p.goto(`/play/characters/${npcs.Brant}`);
  await expect(p.getByRole("link", { name: "← Brant" })).toBeVisible();
  await expect(p.getByLabel("Blood: 9 of 10")).toBeVisible();
  await expect(p.getByLabel("aggravated damage")).toHaveCount(1);
  await expect(p.getByLabel("normal damage")).toHaveCount(0);
  // A tap on the full Play View is on the card, and Undo on the card takes back the newest tap.
  const before = (await state("Cassia")).willpower;
  await p.goto(`/play/characters/${npcs.Cassia}`);
  await p.getByLabel("Quick notes").uncheck();
  await p.getByRole("button", { name: "Spend Willpower", exact: true }).last().click();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await p.goto(sceneUrl);
  const cassia = card("Cassia");
  await expect(cassia.getByLabel(`Willpower: ${before.value - 1} of ${before.most}`)).toBeVisible();
  await cassia.getByRole("button", { name: /^Undo Willpower/ }).click();
  await expect(cassia.getByLabel(`Willpower: ${before.value} of ${before.most}`)).toBeVisible();
  await expect(cassia.getByRole("status")).toHaveText("Saved");
  await expect.poll(async () => (await state("Cassia")).willpower.value).toBe(before.value);
  await cassia.getByRole("button", { name: /^Log/ }).click();
  await expect(cassia.getByText(/^Undid: Willpower/)).toBeVisible();

  // Reset on a card puts that character back, and only that one.
  await brant.getByRole("button", { name: /^Reset/ }).click();
  await brant.getByRole("button", { name: "Reset for next game…" }).click();
  await brant.getByRole("button", { name: "Reset for next game", exact: true }).click();
  await expect(brant.getByLabel("Blood: 10 of 10")).toBeVisible();
  await expect(brant.getByLabel(/^Health: 0 of \d+ marked$/)).toBeVisible();
  await expect(alder.getByLabel("Blood: 8 of 10")).toBeVisible();

  // Removing one takes it off the scene, not out of the troupe.
  await cassia.getByRole("button", { name: "Remove Cassia from the scene" }).click();
  await expect(p.getByRole("article")).toHaveCount(2);
  await expect.poll(pinned).toBe(2);
  await p.reload();
  await expect(p.getByRole("article")).toHaveCount(2);
  await expect(card("Cassia")).toHaveCount(0);
  await search.click();
  await expect(p.getByRole("option", { name: /Cassia/ })).toBeVisible();
  await expect.poll(async () => (await state("Alder")).blood.value).toBe(8);
});

test("a Scene card shows an NPC's best attacks and defences, and its Pools and Powers sections follow a form", async ({ browser }) => {
  const custodian = await person(browser, "pools-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "pools-lead");
  const troupeName = `Court of Hounds ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // An NPC with four attacks and Shape of the Beast: Physical 5, Brawl 3, Melee 2, Firearms 1, Athletics 1, Dodge 2.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Vesper", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  for (const [category, name, rating] of [
    ["clan", "Gangrel", null],
    ["attributes", "Physical", 5],
    ["attributes", "Mental", 3],
    ["skills", "Brawl", 3],
    ["skills", "Melee", 2],
    ["skills", "Firearms", 1],
    ["skills", "Athletics", 1],
    ["skills", "Dodge", 2],
    ["disciplines", "Protean", 4],
  ] as const) {
    const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category, name, rating, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
  }
  await p.goto(`/characters/${npc}/sheet`);
  const choices = p.getByLabel("Shape of the Beast choices");
  await choices.getByRole("button", { name: "choose" }).click();
  await choices.getByLabel("Fight form", { exact: true }).fill("bear");
  await choices.getByLabel("Fight form template").selectOption("Huge");
  await choices.getByRole("button", { name: "Save" }).click();
  await expect(choices).toContainText("fight form bear · fight form template Huge");

  // Pinned: the top three attacks (Thrown, the fourth, is left out) and the defences are on the card.
  await openScene(p, troupeId, "Vesper's hunt");
  await p.getByRole("combobox", { name: "Add to the scene" }).fill("Vesper");
  await p.getByRole("option", { name: /Vesper/ }).click();
  const card = p.getByRole("article", { name: "Vesper" });
  await expect(card).toContainText("Attack Unarmed 8 (1 dmg) · Melee 7");
  await expect(card).toContainText("Firearms 6");
  await expect(card).not.toContainText("Thrown");
  await expect(card).toContainText("Defence Dodge 7");

  // A form in Powers raises the attack and shows as a badge; Undo takes it back.
  await card.getByRole("button", { name: /^Powers/ }).click();
  await card.getByLabel("Shape of the Beast: fight form (bear, Huge) on").check();
  await expect(card).toContainText("Attack Unarmed 10");
  await expect(card.getByText("Shape of the Beast: fight form (bear, Huge)", { exact: true }).first()).toBeVisible();
  await expect(card.getByRole("status")).toHaveText("Saved");
  await card.getByRole("button", { name: /^Undo Turned into Shape of the Beast/ }).click();
  await expect(card).toContainText("Attack Unarmed 8 (1 dmg)");
  await expect(card.getByLabel("Shape of the Beast: fight form (bear, Huge) on")).not.toBeChecked();

  // Pools lists every pool, Combat and Defence first, and stays open over a reload.
  await card.getByRole("button", { name: /^Pools/ }).click();
  await expect(card.getByRole("region", { name: "Combat" })).toContainText("Thrown attack");
  await expect(card.getByRole("region", { name: "Defence" })).toContainText("Resisting Social powers");
  await p.reload();
  await expect(card.getByRole("region", { name: "Combat" })).toBeVisible();
  await expect(card.getByRole("button", { name: /^Powers/ })).toHaveAttribute("aria-expanded", "true");
});

test("two storytellers share a troupe's named scenes: each pins, taps and sees the other's, and the maker renames and removes", async ({ browser }) => {
  test.slow();
  const custodian = await person(browser, "named-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "named-lead");
  const second = await person(browser, "named-storyteller");
  const troupeName = `Court of Tapers ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // A second storyteller and three NPCs, made straight through the API.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const staffed = await p.request.put(`/api/troupes/${troupeId}/staff`, { headers, data: { handle: second.handle, role: "storyteller" } });
  expect(staffed.status(), await staffed.text()).toBe(200);
  const npcs: Record<string, string> = {};
  for (const name of ["Kasimir", "Lorcan", "Odile"]) {
    const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(made.status(), await made.text()).toBe(201);
    npcs[name] = (await made.json()).id;
  }
  const stocked = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Grimsby", npc_form: "stock", stock: { rating: 2 } } });
  expect(stocked.status(), await stocked.text()).toBe(201);

  // The lead's browser still has a scene of its own from before; the old address goes to the list, which offers to save it.
  await p.evaluate(([troupe, odile]) => localStorage.setItem(`horatio.scene.${troupe}`, JSON.stringify([odile])), [troupeId, npcs.Odile!]);
  await p.goto(`/play/troupes/${troupeId}/scene`);
  await expect(p).toHaveURL(new RegExp(`/play/troupes/${troupeId}/scenes$`));
  const offer = p.getByRole("region", { name: "This device's scene" });
  await expect(offer).toContainText("1 character");
  await offer.getByLabel("Name of the scene").fill("Old haunt");
  await offer.getByRole("button", { name: "Save this device's scene" }).click();
  await expect(offer).toHaveCount(0);
  await expect(p.getByRole("listitem", { name: "Old haunt" })).toContainText("Yours · 1 character");
  expect(await p.evaluate((troupe) => localStorage.getItem(`horatio.scene.${troupe}`), troupeId)).toBeNull();
  await p.reload();
  await expect(p.getByRole("listitem", { name: "Old haunt" })).toBeVisible();
  await expect(offer).toHaveCount(0);

  // Two named scenes, with a different NPC in each.
  const search = (page: Page) => page.getByRole("combobox", { name: "Add to the scene" });
  const scenes: Record<string, string> = {};
  for (const [name, npc] of [
    ["Elysium, ballroom", "Lorcan"],
    ["Warehouse ambush", "Kasimir"],
  ] as const) {
    await p.goto(`/play/troupes/${troupeId}/scenes`);
    await p.getByLabel("Name of a new scene").fill(name);
    await p.getByRole("button", { name: "New scene" }).click();
    await expect(p.getByRole("heading", { name, exact: true })).toBeVisible();
    scenes[name] = new URL(p.url()).pathname;
    await search(p).fill(npc);
    await p.getByRole("option", { name: new RegExp(npc) }).click();
    await expect(p.getByRole("article", { name: npc })).toBeVisible();
  }
  await expect(p.getByRole("article")).toHaveCount(1);
  // A Stock NPC has no Play View yet: its card is its name and rating.
  await p.goto(scenes["Elysium, ballroom"]!);
  await search(p).fill("Grimsby");
  await p.getByRole("option", { name: /Grimsby/ }).click();
  await expect(p.getByRole("article", { name: "Grimsby" })).toContainText("Stock NPC · rating 2");
  await expect(p.getByRole("article", { name: "Grimsby" })).toContainText("its Play card comes in a later PR");
  await p.goto(scenes["Warehouse ambush"]!);

  // The second storyteller has none of their own, and sees all three under All, with who made them.
  const s = second.page;
  await s.goto(`/play/troupes/${troupeId}/scenes`);
  await expect(s.getByText("You have no scenes in this troupe yet.")).toBeVisible();
  await s.getByRole("button", { name: "All" }).click();
  await expect(s.getByRole("listitem")).toHaveCount(3);
  const ambush = s.getByRole("listitem", { name: "Warehouse ambush" });
  await expect(ambush).toContainText("By named-lead · 1 character");
  // Not theirs to change.
  await expect(ambush.getByRole("button", { name: "Rename Warehouse ambush" })).toHaveCount(0);

  // They open the ambush, tap for Kasimir and pin Odile there too.
  await ambush.getByRole("link", { name: "Warehouse ambush" }).click();
  await expect(s.getByRole("heading", { name: "Warehouse ambush", exact: true })).toBeVisible();
  await expect(s.getByText("named-lead's scene")).toBeVisible();
  await expect(s.getByRole("button", { name: "Rename" })).toHaveCount(0);
  const kasimir = s.getByRole("article", { name: "Kasimir" });
  await kasimir.getByRole("button", { name: "Spend Blood", exact: true }).click();
  await expect(kasimir.getByLabel("Blood: 9 of 10")).toBeVisible();
  await expect(kasimir.getByRole("status")).toHaveText("Saved");
  await search(s).fill("Odile");
  await s.getByRole("option", { name: /Odile/ }).click();
  await expect(s.getByRole("article")).toHaveCount(2);

  // The lead, with the ambush open, sees the tap and the pin on the next refresh.
  await expect(p.getByRole("article", { name: "Kasimir" }).getByLabel("Blood: 9 of 10")).toBeVisible({ timeout: 25_000 });
  await expect(p.getByRole("article", { name: "Odile" })).toBeVisible({ timeout: 25_000 });
  await p.screenshot(shots("named-scene"));

  // Full view from a card goes back to that scene.
  await p.getByRole("link", { name: "Open the full Play View of Kasimir" }).click();
  await expect(p.getByLabel("Blood: 9 of 10")).toBeVisible();
  await p.getByRole("link", { name: "← Back to the scene" }).click();
  await expect(p).toHaveURL(new RegExp(`${scenes["Warehouse ambush"]}$`));
  await expect(p.getByRole("heading", { name: "Warehouse ambush", exact: true })).toBeVisible();

  // The maker renames one in its heading and removes the other from the list, after asking.
  await p.goto(scenes["Elysium, ballroom"]!);
  await p.getByRole("button", { name: "Rename" }).click();
  await p.getByLabel("Name of the scene").fill("Elysium, gallery");
  await p.getByRole("button", { name: "Save", exact: true }).click();
  await expect(p.getByRole("heading", { name: "Elysium, gallery", exact: true })).toBeVisible();
  await p.getByRole("link", { name: /^← Scenes/ }).click();
  const doomed = p.getByRole("listitem", { name: "Warehouse ambush" });
  await doomed.getByRole("button", { name: "Remove Warehouse ambush" }).click();
  await doomed.getByRole("button", { name: "Remove the scene" }).click();
  await expect(doomed).toHaveCount(0);
  await expect(p.getByRole("listitem", { name: "Elysium, gallery" })).toContainText("2 characters");

  // The second storyteller's list follows; removing the scene left Kasimir as he was.
  await s.goto(`/play/troupes/${troupeId}/scenes`);
  await s.getByRole("button", { name: "All" }).click();
  await expect(s.getByRole("listitem", { name: "Elysium, gallery" })).toBeVisible();
  await expect(s.getByRole("listitem", { name: "Warehouse ambush" })).toHaveCount(0);
  expect((await (await s.request.get(`/api/characters/${npcs.Kasimir}/play`)).json()).blood.value).toBe(9);
  const log = (await (await p.request.get(`/api/troupes/${troupeId}/log`)).json()) as { message: string }[];
  expect(log.map((e) => e.message)).toEqual(
    expect.arrayContaining(["named-lead removed the scene Warehouse ambush.", "named-lead renamed the scene Elysium, ballroom to Elysium, gallery."]),
  );
});

test("a troupe's profile: storytellers fill it in, and people not signed in see it only when it is public", async ({ browser }) => {
  test.slow();
  const custodian = await person(browser, "profile-custodian");
  makeCustodian(custodian.email);
  // The lead plans games in New York; a visitor reads them in Tokyo.
  const lead = await person(browser, "profile-lead", { timezoneId: "America/New_York" });
  const player = await person(browser, "profile-player");
  const visitor = await (await browser.newContext({ timezoneId: "Asia/Tokyo" })).newPage();
  const troupeName = `Lords of Leeds ${run}`;

  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Troupes" }).click();
  await expect(c.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await c.getByLabel("Name").fill(troupeName);
  await c.getByLabel("Lead storyteller").fill(lead.handle);
  await c.getByRole("button", { name: "Create troupe" }).click();
  await expect(c.getByRole("link", { name: troupeName })).toBeVisible();

  // The lead fills in the profile on the troupe's Profile tab.
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  const troupeUrl = l.url();
  const troupeId = troupeUrl.split("/troupes/")[1]!.split("/")[0]!;
  await l.getByRole("link", { name: "Profile", exact: true }).click();
  await l.getByRole("button", { name: "Edit profile" }).click();
  // A portrait, cropped square like a character's picture.
  await l.getByRole("button", { name: "Add a portrait" }).click();
  await l.getByLabel("Choose a portrait").setInputFiles("e2e/portrait.jpg");
  await expect(l.getByRole("slider", { name: /Where the portrait is/ })).toBeVisible();
  await l.getByRole("button", { name: "Save picture" }).click();
  await expect(l.getByRole("dialog")).toBeHidden();
  await l.getByLabel("Website").fill("https://lords.example.org");
  await l.getByLabel("Discord invite").fill("https://discord.gg/lords");
  await l.getByLabel("How often games run").fill("Second Saturday of the month, 7 pm to midnight");
  // A game: its end starts five hours on.
  await l.getByLabel("Game starts").fill("2030-01-12T19:00");
  await expect(l.getByLabel("Game ends")).toHaveValue("2030-01-13T00:00");
  await l.getByRole("button", { name: "Add game" }).click();
  await expect(l.getByRole("list", { name: "Upcoming games to edit" }).getByText("Sat 12 Jan 2030, 7 pm to Sun 13 Jan 2030, 12 am EST")).toBeVisible();
  await l.getByLabel("City or region").fill("Leeds");
  await l.getByLabel("Venue name").fill("The Crypt");
  await l.getByLabel("Address", { exact: true }).fill("12 Mill Lane, Leeds");
  await l.getByLabel("Accessibility").fill("Step-free access and a quiet room.");
  await l.getByLabel("Chronicle").fill("Leeds by Night");
  await l.getByLabel("Era").fill("Modern nights");
  await l.getByLabel("Tone").fill("Slow-burning political horror.");
  await l.getByLabel("Taking new players?").selectOption({ label: "Welcoming new players" });
  await l.getByLabel("Contact for new players").selectOption({ label: `profile-lead (@${lead.handle})` });
  await l.getByLabel("Minimum age").fill("18");
  await l.getByLabel("Content notes").fill("Violence and body horror.");
  await l.screenshot(shots("troupe-profile-edit"));
  await l.getByRole("button", { name: "Save profile" }).click();

  // It shows on the troupe page, with the next game in the lead's own zone.
  await expect(l.getByText("Sat 12 Jan 2030, 7 pm EST")).toBeVisible();
  await expect(l.getByText("Welcoming new players")).toBeVisible();
  await expect(l.getByText("12 Mill Lane, Leeds")).toBeVisible();
  await expect(l.getByText("18+")).toBeVisible();
  const website = l.getByRole("link", { name: "Website" });
  await expect(website).toHaveAttribute("href", "https://lords.example.org");
  await expect(website).toHaveAttribute("target", "_blank");
  await expect(l.getByRole("heading", { level: 1 }).locator('img[src*="/portraits/"]')).toBeVisible();
  await l.screenshot(shots("troupe-profile"));

  // Anyone signed in sees it, street address and all; and the portrait shows in the troupe list.
  const p = player.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await expect(p.getByRole("link", { name: troupeName }).locator('img[src*="/portraits/"]')).toBeVisible();
  await p.getByRole("link", { name: troupeName }).click();
  await p.getByRole("link", { name: "Profile", exact: true }).click();
  await expect(p.getByText("12 Mill Lane, Leeds")).toBeVisible();
  await expect(p.getByRole("button", { name: "Edit profile" })).toHaveCount(0);
  await expect(p.getByRole("switch", { name: "Public" })).toHaveCount(0);

  // Off, as it starts: someone not signed in is told nothing about it.
  await visitor.goto(`/t/${troupeId}`);
  await expect(visitor.getByText(/only for people signed in, or there is no such troupe/)).toBeVisible();
  await expect(visitor.getByText(troupeName)).toHaveCount(0);

  // Switched on: anyone can see it at its public address, but never the street address.
  await l.getByRole("switch", { name: "Public" }).click();
  await expect(l.getByText("Public: anyone can see this profile, even people not signed in")).toBeVisible();
  await visitor.reload();
  await expect(visitor.getByRole("heading", { name: troupeName })).toBeVisible();
  await expect(visitor.getByText("The Crypt")).toBeVisible();
  await expect(visitor.getByText("to see the address.")).toBeVisible();
  await expect(visitor.getByText("12 Mill Lane")).toHaveCount(0);
  await expect(visitor.getByText(lead.email)).toHaveCount(0);
  await expect(visitor.getByText(`@${lead.handle}`).first()).toBeVisible();
  // The next game, in the visitor's own zone.
  await expect(visitor.getByText("Sun 13 Jan 2030, 9 am GMT+9")).toBeVisible();
  await expect(visitor.locator('img[src*="/portraits/"]').first()).toBeVisible();
  await visitor.screenshot(shots("troupe-profile-public"));
  // A link to it previews with the troupe's name and portrait.
  const shared = await (await visitor.request.get(`/t/${troupeId}`)).text();
  expect(shared).toContain(`<meta property="og:title" content="${troupeName}" />`);
  expect(shared).toMatch(/<meta property="og:image" content="[^"]*\/portraits\/[^"]*\/512\.webp" \/>/);

  // Switched off again, it is for people signed in only once more.
  await l.getByRole("switch", { name: "Public" }).click();
  await expect(l.getByText("Signed-in only")).toBeVisible();
  await visitor.reload();
  await expect(visitor.getByText(/only for people signed in, or there is no such troupe/)).toBeVisible();
});

test("Gossip is filled from the influence log, and a discovery block hides an entry from it", async ({ browser }) => {
  // A whole character creation, then a downtime answered from the log.
  test.slow();
  const custodian = await person(browser, "gossip-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "gossip-lead");
  const player = await person(browser, "gossip-player");
  const troupeName = `Court of Rumours ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };

  // Agnes is built for the troupe, then takes Elite 3 with News Media, and joins it.
  const p = player.page;
  await p.reload();
  await p.getByLabel("Name").fill("Agnes");
  await p.getByLabel("Build for").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Create" }).click();
  await p.getByLabel("Clan").selectOption("Brujah");
  await expect(p.getByLabel("Clan")).toHaveValue("Brujah");
  await p.getByLabel("Sect").selectOption("Camarilla");
  const next = async (heading: string) => {
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
  };
  const tap = async (...dots: string[]) => {
    for (const dot of dots) await p.getByRole("button", { name: dot, exact: true }).click();
  };
  await next("Attributes");
  await tap("Physical 7", "Social 5", "Mental 3");
  await next("Focuses");
  await tap("Strength 1", "Wits 1", "Charisma 1");
  await next("Skills");
  await tap("Brawl 4", "Dodge 3", "Athletics 3", "Awareness 2", "Empathy 2", "Firearms 2");
  await tap("Investigation 1", "Leadership 1", "Medicine 1", "Melee 1");
  await next("Backgrounds");
  await tap("Fame 3", "Herd 2", "Generation 1");
  await next("Disciplines");
  await tap("Celerity 2", "Potence 1", "Presence 1");
  await next("Merits & flaws");
  await next("Review");
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  const agnes = new URL(p.url()).pathname.split("/")[2]!;
  for (const [category, name, rating] of [
    ["backgrounds", "Influences: The Elite", 3],
    ["influence_elite_specializations", "News Media", 1],
  ] as const) {
    const bought = await p.request.put(`/api/characters/${agnes}/traits`, { headers, data: { category, name, rating } });
    expect(bought.status(), await bought.text()).toBe(200);
  }
  const asked = await p.request.post(`/api/characters/${agnes}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBe(201);
  const approved = await l.request.post(`/api/approvals/${(await asked.json()).id}/approve`, { headers, data: {} });
  expect(approved.status(), await approved.text()).toBe(200);

  // A cycle, and the troupe's log: three Elite actions by someone else in News Media, one
  // of them blocked once and one too long ago, and one of Agnes's own.
  const day = 24 * 60 * 60 * 1000;
  const closes = new Date(Date.now() + 7 * day);
  const made = await l.request.post(`/api/troupes/${troupeId}/cycles`, {
    headers,
    data: { name: "Winter", closes_at: closes.toISOString(), grace_ends_at: new Date(closes.getTime() + 7 * day).toISOString() },
  });
  expect(made.status(), await made.text()).toBe(201);
  const cycleId = (await made.json()).id;
  expect((await l.request.post(`/api/cycles/${cycleId}/open`, { headers })).status()).toBe(200);
  for (const [who, action_key, purpose, daysBeforeClose, blocks] of [
    ["REDACTED", "smooth_over", "To bury the mayor's scandal", 17, 0],
    ["REDACTED", "no_party_crashers", "To keep the press out of the gala", 100, 0],
    ["agnes", "a_friend_in_need", "To call in a favour from the editor", 12, 0],
    ["REDACTED", "bureaucratic_errors", "To lose the dock permits", 27, 1],
  ] as const) {
    const data = {
      type: "elite",
      happened_at: new Date(closes.getTime() - daysBeforeClose * day).toISOString(),
      ...(who === "agnes" ? { character_id: agnes } : { name: who }),
      specialization: "News Media",
      action_key,
      purpose,
      blocks,
    };
    const logged = await l.request.post(`/api/troupes/${troupeId}/influence-log`, { headers, data });
    expect(logged.status(), await logged.text()).toBe(201);
  }

  // Agnes spends two actions on Gossip, and one hiding her own favour from the editor.
  await p.goto(`/characters/${agnes}/downtime`);
  const elite = p.locator("section").filter({ has: p.getByRole("heading", { name: "Elite influence action" }) });
  const answer = async (i: number, text: string, action: string) => {
    await elite.getByRole("button", { name: /Add an action/ }).click();
    await elite.getByLabel("Elite influence action").nth(i).fill(text);
    await elite.getByLabel("Specialisation").nth(i).selectOption("News Media");
    await elite.getByLabel("Action", { exact: true }).nth(i).selectOption({ label: action });
  };
  await answer(0, "Ask the newsroom what is stirring.", "2: Gossip and Insider Trading");
  await expect(elite.getByText("Covers all your specialisations; more actions find better-hidden things.")).toBeVisible();
  await answer(1, "Ask again at the Herald.", "2: Gossip and Insider Trading");
  await answer(2, "Bury the favour I called in from the editor.", "Discovery block");
  await elite.getByLabel("Whose action to hide").selectOption({ label: "One of mine" });
  // Only her own actions to pick from, by their ids.
  const own = elite.getByLabel("Your action").locator("option", { hasText: "To call in a favour from the editor" });
  await expect(own).toHaveText(/^E3 · /);
  await expect(elite.getByLabel("Your action").locator("option")).toHaveCount(2);
  await elite.getByLabel("Your action").selectOption((await own.getAttribute("value"))!);
  await p.getByRole("button", { name: "Submit downtime" }).click();
  await expect(p.getByText("submitted", { exact: true })).toBeVisible();

  // The lead fills the first Gossip answer from the log: the result goes on the last,
  // strength 2, so the once-blocked entry shows, and never Agnes's own or who took them.
  await l.goto(`/cycles/${cycleId}/responses`);
  const responses = l.getByRole("textbox", { name: "Response to Agnes" });
  await l.getByRole("button", { name: "Fill from the log" }).first().click();
  await expect(responses.nth(0)).toHaveValue("Combined with your other Gossip and Insider Trading actions: strength 2, results below.");
  const result = l.getByRole("textbox", { name: "Combined response: Ask again at the Herald." });
  await expect(result).toHaveValue(/^Gossip and Insider Trading, strength 2, in News Media, since .*:\n- .*, News Media, 3: Bureaucratic Errors, To lose the dock permits \(E4\)\n- .*, News Media, 4: Smooth Over, To bury the mayor's scandal \(E1\)$/);
  await l.screenshot(shots("gossip"));
  await l.getByRole("button", { name: "Save response" }).first().click();
  await expect(responses.nth(1)).toHaveValue(/To bury the mayor's scandal \(E1\)$/);

  // The block, on the entry Agnes picked.
  await expect(l.getByLabel("Entry to block").locator("option:checked")).toHaveText(/^E3 · .* · Agnes · Elite, News Media · 1: A Friend in Need/);
  await l.getByRole("button", { name: "Accept the block" }).click();
  await expect(l.getByText("Blocked E3 (now 1).")).toBeVisible();
  await expect(responses.nth(2)).toHaveValue("Blocked (now 1).");

  // The log shows where the block came from.
  await l.goto(`/troupes/${troupeId}/influence`);
  const e3 = l.getByRole("listitem", { name: "Entry E3" });
  await expect(e3.getByText("1 block")).toBeVisible();
  await expect(e3.getByText(/Blocked by Agnes in Winter, accepted by gossip-lead/)).toBeVisible();

  // A longer lookback finds the action from 100 days back.
  await l.goto(`/troupes/${troupeId}/rules/actions`);
  await expect(l.getByText("90 days", { exact: true })).toBeVisible();
  await l.getByRole("button", { name: "Change how far lookups look back" }).click();
  await l.getByLabel("Days to look back").fill("120");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("120 days", { exact: true })).toBeVisible();
  await l.goto(`/cycles/${cycleId}/responses`);
  await l.getByRole("button", { name: "Fill from the log" }).first().click();
  await expect(l.getByRole("textbox", { name: "Combined response: Ask again at the Herald." })).toHaveValue(/To keep the press out of the gala \(E2\)/);
});

test("a storyteller resolves an attack, its target's Defend taken off, and the target's influence counts lower", async ({ browser }) => {
  const custodian = await person(browser, "attack-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "attack-lead");
  const troupeName = `Court of Knives ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Two NPCs, made straight through the API: Isolde with Elite 4, Vasquez with Elite 3.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const npcs: Record<string, string> = {};
  for (const [name, elite] of [
    ["Isolde", 4],
    ["Vasquez", 3],
  ] as const) {
    const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(made.status(), await made.text()).toBe(201);
    npcs[name] = (await made.json()).id;
    const rated = await p.request.put(`/api/characters/${npcs[name]}/npc/ratings`, {
      headers,
      data: { category: "backgrounds", name: "Influences: The Elite", rating: elite, detail: "" },
    });
    expect(rated.status(), await rated.text()).toBe(200);
  }
  // Vasquez defended a minute ago, before the attack.
  const defended = await p.request.post(`/api/troupes/${troupeId}/influence-log`, {
    headers,
    data: { type: "elite", happened_at: new Date(Date.now() - 60_000).toISOString(), character_id: npcs.Vasquez, action_key: "defend" },
  });
  expect(defended.status(), await defended.text()).toBe(201);

  // The lead logs Isolde's attack on Vasquez's Elite, 4 actions: 2 levels.
  await p.goto(`/troupes/${troupeId}/influence`);
  await p.getByRole("button", { name: "Log influence" }).click();
  const form = p.getByRole("form", { name: "Log influence" });
  await form.getByLabel("Who", { exact: true }).fill("Isolde");
  await form.getByRole("option", { name: "Isolde NPC" }).click();
  await form.getByLabel("Action", { exact: true }).selectOption({ label: "Attack" });
  await form.getByLabel("Attacking").selectOption({ label: "Vasquez (NPC)" });
  await form.getByLabel("Times taken").fill("4");
  await form.getByRole("button", { name: "Log it" }).click();
  const attack = p.getByRole("listitem", { name: "Entry E2" });
  await expect(attack.getByText("Attack → Vasquez's Elite")).toBeVisible();

  // Resolving it shows the cost and the Defend taken off.
  await attack.getByRole("button", { name: "Resolve" }).click();
  const dialog = p.getByRole("dialog");
  await expect(dialog.getByText("An attack on Vasquez's Elite, at 3 now.")).toBeVisible();
  await expect(dialog.getByText("2 levels at 2 actions each: 4 actions. E2 spent 4.")).toBeVisible();
  await expect(dialog.getByLabel("Defends")).toContainText("Vasquez's Defends (E1) take 1 level off. Vasquez loses 1 level and as many actions");
  await p.screenshot(shots("influence-resolve"));
  await dialog.getByRole("button", { name: "Record the attack" }).click();
  await expect(attack.getByText("Elite 1 lower")).toBeVisible();
  await p.getByRole("navigation", { name: "Influence log" }).getByRole("link", { name: "Effects and blocks" }).click();
  await expect(p.getByRole("list", { name: "Effects and blocks" }).getByText("Vasquez: Elite 1 lower (1 defended)")).toBeVisible();

  // Vasquez's sheet shows it, and the Play View's Elite counter starts lower.
  await p.goto(`/characters/${npcs.Vasquez}/sheet`);
  await expect(p.getByRole("heading", { name: "Influence changed" })).toBeVisible();
  await expect(p.getByText(/\(attacked\), until .*, or 2 more games if that is later/)).toBeVisible();
  await p.goto(`/play/characters/${npcs.Vasquez}`);
  const elite = p.getByRole("listitem").filter({ hasText: "Influences: The Elite" });
  await expect(elite.getByText("2 of 2 left", { exact: false })).toBeVisible();

  // Taken back, the counter is whole again.
  await p.goto(`/troupes/${troupeId}/influence/effects`);
  p.once("dialog", (d) => void d.accept());
  await p.getByRole("list", { name: "Effects and blocks" }).getByRole("button", { name: "Take back" }).click();
  await expect(p.getByText("Nothing holding now.")).toBeVisible();
  await p.goto(`/play/characters/${npcs.Vasquez}`);
  await expect(p.getByRole("listitem").filter({ hasText: "Influences: The Elite" }).getByText("3 of 3 left", { exact: false })).toBeVisible();
});

test("Crafts, Performance and Science take a field in the wizard, kept through Back and a reload", async ({ browser }) => {
  const { page: p } = await person(browser, "fielder");
  await p.getByLabel("Name").fill("Lark");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  await p.getByLabel("Clan").selectOption("Brujah");
  await expect(p.getByLabel("Clan")).toHaveValue("Brujah");
  const next = async (heading: string) => {
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
  };
  const tap = async (...dots: string[]) => {
    for (const dot of dots) await p.getByRole("button", { name: dot, exact: true }).click();
  };
  await next("Attributes");
  await tap("Physical 7", "Social 5", "Mental 3");
  await next("Focuses");
  await tap("Strength 1", "Wits 1", "Charisma 1");
  await next("Skills");

  // Choosing Performance asks for its field there and then.
  await tap("Performance 3");
  await expect(p.getByLabel("Performance field")).toBeFocused();
  await expect(p.getByLabel("Performance field")).toHaveAttribute("placeholder", "Such as Singing");
  await p.getByLabel("Performance field").fill("Singing");
  // A second field of the same skill has its own dots.
  await p.getByRole("button", { name: "Add another field" }).click();
  await expect(p.getByLabel("Performance #2 field")).toBeFocused();
  await p.getByLabel("Performance #2 field").fill("Dance");
  await tap("Performance #2 1");
  await tap("Brawl 4", "Science 3", "Awareness 2", "Empathy 2", "Firearms 2", "Investigation 1", "Leadership 1", "Medicine 1");
  // Science has no field yet: the row says so, and the step will not move on.
  await expect(p.getByText("Science needs a field.")).toBeVisible();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByText(/Before moving on: Crafts, Performance and Science need a field/)).toBeVisible();
  await expect(p.getByRole("heading", { name: "Skills", exact: true })).toBeVisible();
  await p.screenshot(shots("creation-fields"));
  await p.getByLabel("Science field").fill("Chemistry");
  await expect(p.getByText("Science needs a field.")).toHaveCount(0);
  await next("Backgrounds");

  // The fields are kept going Back, and through a reload.
  await p.getByRole("button", { name: "Back" }).click();
  await expect(p.getByRole("heading", { name: "Skills", exact: true })).toBeVisible();
  await expect(p.getByLabel("Performance field")).toHaveValue("Singing");
  await expect(p.getByLabel("Performance #2 field")).toHaveValue("Dance");
  await p.reload();
  await expect(p.getByLabel("Science field")).toHaveValue("Chemistry");
  await expect(p.getByRole("button", { name: "Performance #2 1", exact: true })).toHaveAttribute("aria-pressed", "true");
  await next("Backgrounds");
  await tap("Fame 3", "Herd 2", "Generation 1");
  await next("Disciplines");
  await tap("Celerity 2", "Potence 1", "Presence 1");
  await next("Merits & flaws");

  // A pick placed without its field elsewhere (as on the Sheet tab) is given one on Review.
  const id = new URL(p.url()).pathname.split("/")[2]!;
  const creation = await (await p.request.get(`/api/characters/${id}/creation`)).json();
  const skills = creation.pools
    .filter((pool: { category: string }) => pool.category === "skills")
    .flatMap((pool: { traits: { name: string; detail: string; pick: number }[] }) => pool.traits)
    .map((t: { name: string; detail: string; pick: number }) => (t.name === "Medicine" ? { name: "Crafts", detail: "", rating: 1 } : { name: t.name, detail: t.detail, rating: t.pick }));
  const placed = await p.request.put(`/api/characters/${id}/creation/categories/skills`, { headers: { "X-Horatio": "1" }, data: { picks: skills } });
  expect(placed.status(), await placed.text()).toBe(200);
  await p.goto(`/characters/${id}/create/review`);
  await expect(p.getByText(/Performance: Singing, Science: Chemistry/)).toBeVisible();
  await expect(p.getByText("Crafts needs a field:")).toBeVisible();
  await expect(p.getByRole("link", { name: "Back to Skills" })).toBeVisible();
  await expect(p.getByRole("button", { name: "Finish creation" })).toBeDisabled();
  await p.getByLabel("Crafts field").fill("Woodwork");
  await p.getByRole("button", { name: "Set" }).click();
  await expect(p.getByText("Crafts needs a field:")).toHaveCount(0);
  await expect(p.getByText(/Crafts: Woodwork/)).toBeVisible();
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Character creation" })).toHaveCount(0);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  for (const skill of ["Performance: Singing", "Performance: Dance", "Science: Chemistry", "Crafts: Woodwork"])
    await expect(part("Skills").getByText(skill, { exact: true })).toBeVisible();
});

/** A finished vampire built through the API, with self-entered XP to spend. */
async function builtVampire(p: Page, name: string, clan: string, build: Record<string, [string, number][]>, raises: [string, string, number][] = []) {
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: clan, rating: null });
  for (const [category, picks] of Object.entries(build))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});
  await send("POST", `/api/characters/${id}/xp/self-entered`, { amount: 200, reason: "Played elsewhere" });
  for (const [category, trait, rating] of raises) await send("PUT", `/api/characters/${id}/traits`, { category, name: trait, rating });
  return id as string;
}

const ATTRIBUTES_AND_FOCUSES: Record<string, [string, number][]> = {
  attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
  focus_physicals: [["Strength", 1]],
  focus_mentals: [["Wits", 1]],
  focus_socials: [["Charisma", 1]],
  skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
};

test("the sheet points to the techniques and elder powers a character can take", async ({ browser }) => {
  const { page: p } = await person(browser, "finder-player");
  // A Pretender Elder (Generation 3) with Celerity 5: one elder power, and techniques at 20 XP.
  const id = await builtVampire(
    p,
    "Wren",
    "Brujah",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 3], ["Herd", 2], ["Fame", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] },
    [["disciplines", "Celerity", 5]],
  );
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const disciplines = part("Disciplines");
  const chips = p.getByRole("navigation", { name: "Categories" });

  // One quiet line says what is open, and opens the Add panel there.
  await expect(disciplines.getByText(/Elder Disciplines? open to you\.$/)).toBeVisible();
  await p.screenshot(shots("open-to-you"));
  await disciplines.getByRole("button", { name: /^\d+ Elder Disciplines?$/ }).click();
  await expect(chips.getByRole("button", { name: /^Elder Disciplines/ })).toHaveAttribute("aria-pressed", "true");
  await expect(chips.getByRole("button", { name: /^Techniques/ })).toBeVisible();
  // Rituals need a ritual discipline, which a Brujah has not got.
  await expect(chips.getByRole("button", { name: /^Rituals/ })).toHaveCount(0);
  // What this character can take, by default: Celerity's elder powers, not Animalism's.
  await expect(p.getByLabel("Show")).toHaveValue("can");
  await expect(p.getByPlaceholder(/you can take…$/)).toBeVisible();
  await expect(p.getByRole("button", { name: "Celerity: Projectile" })).toBeVisible();
  await expect(p.getByRole("button", { name: /^Animalism: / })).toHaveCount(0);
  await expect(p.getByText(/^\d+ more you can't take:/)).toBeVisible();
  await p.getByLabel("Show").selectOption({ label: "Everything" });
  await expect(p.getByRole("button", { name: /^Animalism: / }).first()).toBeDisabled();
  await expect(p.getByText("An elder power needs all 5 dots of its discipline first.", { exact: false }).first()).toBeVisible();
  await p.screenshot(shots("elder-powers"));

  // A power's name finds it in whichever category it lives.
  await p.getByLabel("Search Elder Disciplines").fill("Fearful");
  await p.getByRole("button", { name: "Found in Techniques: Fearful Blow" }).click();
  await expect(chips.getByRole("button", { name: /^Techniques/ })).toHaveAttribute("aria-pressed", "true");
  await expect(p.getByRole("button", { name: /^Fearful Blow/ })).toBeDisabled();
  await expect(p.getByText("Fearful Blow needs Potence 2 and Presence 2.", { exact: false })).toBeVisible();

  // Dots in the cart open the technique straight away, before spending.
  await p.getByRole("button", { name: "Raise Potence" }).click();
  await p.getByRole("button", { name: "Raise Presence" }).click();
  await p.getByLabel("Show").selectOption({ label: "What this character can take" });
  await p.getByRole("button", { name: /^Fearful Blow/ }).click();
  // Pricing the cart is slow work for the server, the more so with the dry runs
  // for each dot still going: wait for the one that prices all three lines.
  const priced = p.waitForResponse((r) => r.url().endsWith(`/api/characters/${id}/cart`) && r.request().postDataJSON()?.changes?.length === 3);
  await p.getByRole("button", { name: "Add to cart" }).click();
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  await priced;
  await expect(cart.getByRole("listitem").filter({ hasText: "Add Fearful Blow" })).toContainText("20 XP");

  // A Pretender Elder learns one elder power: with one in the cart, none are left to take.
  await disciplines.getByRole("button", { name: "Add" }).click();
  await chips.getByRole("button", { name: /^Elder Disciplines/ }).click();
  await p.getByRole("button", { name: "Celerity: Projectile" }).click();
  await p.getByRole("button", { name: "Add to cart" }).click();
  await disciplines.getByRole("button", { name: "Add" }).click();
  await chips.getByRole("button", { name: /^Elder Disciplines/ }).click();
  await expect(chips.getByRole("button", { name: "Elder Disciplines", exact: true })).toBeVisible();
  await expect(p.getByText(/^None you can take\. \d+ you can't:/)).toBeVisible();
  await p.getByRole("button", { name: "show", exact: true }).click();
  await expect(p.getByLabel("Show")).toHaveValue("all");
  await expect(p.getByText("A Pretender Elder can learn only one elder power.", { exact: false }).first()).toBeVisible();
});

test("only a character with a ritual discipline sees rituals, up to its path's level", async ({ browser }) => {
  const { page: p } = await person(browser, "finder-ritualist");
  const id = await builtVampire(p, "Odile", "Tremere", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Thaumaturgy: Path of Blood", 2], ["Auspex", 1], ["Dominate", 1]],
  });
  const rules = await (await p.request.get("/api/rules/vampire")).json();
  const ritual = (level: number) => rules.traits.find((t: { category: string; name: string; fixed_rating: number }) => t.category === "rituals" && t.name.startsWith("Thaumaturgy: ") && t.fixed_rating === level).name as string;
  await p.goto(`/characters/${id}`);
  const disciplines = p.locator("section").filter({ has: p.getByRole("heading", { name: "Disciplines", exact: true }) });
  const chips = p.getByRole("navigation", { name: "Categories" });

  await expect(disciplines.getByRole("button", { name: /^\d+ Rituals$/ })).toBeVisible();
  await disciplines.getByRole("button", { name: /^\d+ Rituals$/ }).click();
  await expect(chips.getByRole("button", { name: /^Rituals/ })).toHaveAttribute("aria-pressed", "true");
  await p.getByLabel("Search Rituals").fill(ritual(1));
  await expect(p.getByRole("button", { name: new RegExp(`^${ritual(1)}`) })).toBeEnabled();
  // A ritual of each level comes before one of the next.
  await p.getByLabel("Search Rituals").fill(ritual(2));
  await expect(p.getByText("None you can take. 1 you can't:")).toBeVisible();
  await p.getByRole("button", { name: "show", exact: true }).click();
  await expect(p.getByText("A thaumaturge learns a ritual of each level before one of the next.", { exact: false })).toBeVisible();
  await p.getByLabel("Search Rituals").fill(ritual(3));
  // Left out of what the character can take, but a tap away, with the reason.
  await expect(p.getByText("A level 3 Thaumaturgy ritual needs a path of Thaumaturgy at 3 or more.", { exact: false })).toBeVisible();
});

test("a Tremere names Path of Corruption as the primary path, once it is the first to 2 dots", async ({ browser }) => {
  const { page: p } = await person(browser, "primary-tremere");
  const id = await builtVampire(p, "Lucita", "Tremere", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Auspex", 2], ["Thaumaturgy: Path of Blood", 1], ["Dominate", 1]],
  });
  const put = async (category: string, name: string, rating: number, detail = "") => {
    const response = await p.request.fetch(`/api/characters/${id}/traits`, { method: "PUT", headers: { "X-Horatio": "1" }, data: { category, name, rating, detail } });
    expect(response.status(), await response.text()).toBeLessThan(300);
  };
  const corruption = "Thaumaturgy: Path of Corruption";
  await put("merits", "Thaumaturgic Expertise", 1, corruption);
  await put("disciplines", corruption, 1);
  await p.goto(`/characters/${id}`);

  // The in-clan path is primary until another is named.
  const picker = p.getByLabel("Primary path of Thaumaturgy");
  await expect(picker).toHaveValue("Thaumaturgy: Path of Blood");
  await expect(picker.getByRole("option", { name: "Path of Blood (in-clan)" })).toBeAttached();
  await picker.selectOption({ label: "Path of Corruption" });
  await expect(picker).toHaveValue(corruption);

  // Named, it can reach 2 dots first, and nothing is flagged for it.
  await put("disciplines", corruption, 2);
  await p.reload();
  await expect(p.getByLabel("Primary path of Thaumaturgy")).toHaveValue(corruption);
  await expect(p.getByText("No path of Thaumaturgy can go above the primary path.")).toHaveCount(0);
  await p.screenshot(shots("primary-path-named"));

  // Path of Blood is no longer the highest, so it cannot be named back yet.
  await p.getByLabel("Primary path of Thaumaturgy").selectOption({ label: "Path of Blood (in-clan)" });
  await expect(p.getByText("Thaumaturgy: Path of Corruption is higher", { exact: false })).toBeVisible();
});

test("a troupe's Profile tab switches it public at once, About sets its XP range, and Waiting on you leads to the work", async ({ browser }) => {
  const custodian = await person(browser, "tidy-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tidy-lead");
  const player = await person(browser, "tidy-player");
  const visitor = await (await browser.newContext()).newPage();
  const troupeName = `Court of Thresholds ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // About, for the lead: nothing is waiting yet.
  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;
  const waiting = l.locator("section").filter({ has: l.getByRole("heading", { name: "Waiting on you" }) });
  await expect(waiting.getByText("Nothing waiting.")).toBeVisible();

  // Profile: the Public switch saves as soon as it is changed.
  await l.getByRole("link", { name: "Profile", exact: true }).click();
  const publicSwitch = l.getByRole("switch", { name: "Public" });
  await expect(publicSwitch).not.toBeChecked();
  await expect(l.getByText("Signed-in only")).toBeVisible();
  await visitor.goto(`/t/${troupeId}`);
  await expect(visitor.getByText(/only for people signed in, or there is no such troupe/)).toBeVisible();
  await publicSwitch.click();
  await expect(publicSwitch).toBeChecked();
  await expect(l.getByText("Public: anyone can see this profile, even people not signed in")).toBeVisible();
  await expect(l.getByText(`/t/${troupeId}`)).toBeVisible();
  await l.reload();
  await expect(l.getByRole("switch", { name: "Public" })).toBeChecked();
  await visitor.reload();
  await expect(visitor.getByRole("heading", { name: troupeName })).toBeVisible();
  // The lead's name and description are here too, and archiving under its own heading.
  await l.getByLabel("Description").fill("A court that meets where the roads cross.");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByRole("region", { name: "Profile" }).getByText("A court that meets where the roads cross.")).toBeVisible();
  await expect(l.getByRole("heading", { name: "Archive the troupe" })).toBeVisible();
  await l.screenshot(shots("troupe-profile-tab"));

  // About: the lead sets the XP floor and ceiling by hand, with Award XP beside them.
  await l.getByRole("link", { name: "About", exact: true }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}$`));
  // The Profile tab's form can linger a moment after the URL changes, with the description in it.
  await expect(l.getByRole("textbox", { name: "Description" })).toHaveCount(0);
  await expect(l.getByText("A court that meets where the roads cross.")).toBeVisible();
  await expect(l.locator("main").getByRole("link", { name: "Award XP", exact: true })).toBeVisible();
  await l.getByRole("button", { name: "Set by hand" }).click();
  await l.getByLabel("Floor", { exact: true }).fill("60");
  await l.getByLabel("Ceiling", { exact: true }).fill("75");
  await l.getByLabel("Why", { exact: true }).fill("Chronicle began in 2021");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("(30 starting + 30 set by hand)")).toBeVisible();
  await expect(l.getByText("(30 starting + 45 set by hand)")).toBeVisible();
  // Starting points keeps a copy to read, which leads back to About.
  await l.goto(`/troupes/${troupeId}/rules/starting`);
  await expect(l.getByText("60 XP", { exact: true })).toBeVisible();
  await expect(l.getByRole("button", { name: "Set by hand" })).toHaveCount(0);
  await l.getByRole("link", { name: "Set them on About" }).click();
  await expect(waiting).toBeVisible();

  // A player asks for the troupe to be their character's home: an approval waits.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Hollis" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
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
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});
  await send("POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });

  // Waiting on you says so, and its line goes straight to Approvals.
  await l.reload();
  const approvals = waiting.getByRole("link", { name: /Approvals waiting/ });
  await expect(approvals).toContainText("1");
  await l.screenshot(shots("troupe-about"));
  await approvals.click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/approvals$`));
  await expect(l.getByText("Hollis").first()).toBeVisible();

  // The player sees About without the box, and the XP range only to read.
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByRole("heading", { name: "XP floor and ceiling" })).toBeVisible();
  await expect(p.getByText("60 XP", { exact: true })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Waiting on you" })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Set by hand" })).toHaveCount(0);
});

test("a troupe takes ghouls once its storytellers tick Ghoul on About, and a ghoul can then join", async ({ browser }) => {
  const custodian = await person(browser, "splat-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "splat-lead");
  const player = await person(browser, "splat-player");
  const troupeName = `Thrall Court ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  const l = lead.page;
  await l.getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;

  // A player builds a ghoul, bound to a domitor not in Horatio; the troupe takes vampires only.
  const p = player.page;
  const send = (method: "POST" | "PUT", url: string, data: object) => p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
  const made = await send("POST", "/api/characters", { splat: "ghoul", name: "Renfield", domitor: { name: "Count Orlok", clan: "Nosferatu" } });
  expect(made.status(), await made.text()).toBe(201);
  const { id } = await made.json();
  const refused = await send("POST", `/api/characters/${id}/troupes`, { troupe_id: troupeId });
  expect(refused.status()).toBe(409);
  expect((await refused.json()).detail).toBe(`${troupeName} does not take ghoul characters.`);

  // The lead ticks Ghoul. Vampire, the only splat ticked until then, could not be unticked.
  const splats = l.locator("section").filter({ has: l.getByRole("heading", { name: "Splats", exact: true }) });
  await expect(splats.getByRole("checkbox", { name: "Vampire" })).toBeChecked();
  await expect(splats.getByRole("checkbox", { name: "Vampire" })).toBeDisabled();
  await expect(splats.getByRole("checkbox", { name: "Ghoul" })).not.toBeChecked();
  // The box follows the troupe as saved, so it ticks once the change is in.
  await splats.getByRole("checkbox", { name: "Ghoul" }).click();
  await expect(splats.getByRole("checkbox", { name: "Ghoul" })).toBeChecked();
  await expect(splats.getByRole("checkbox", { name: "Vampire" })).toBeEnabled();
  await l.reload();
  await expect(splats.getByRole("checkbox", { name: "Ghoul" })).toBeChecked();

  // Now the ghoul joins, and the player reads which splats may.
  const joined = await send("POST", `/api/characters/${id}/troupes`, { troupe_id: troupeId });
  expect(joined.status(), await joined.text()).toBe(201);
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByText("Vampire and Ghoul player characters may join.")).toBeVisible();
});

test("a player asks staff for an elder power the rules refuse, free, and a storyteller approves it", async ({ browser }) => {
  const custodian = await person(browser, "exc-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "exc-lead");
  const player = await person(browser, "exc-player");
  const troupeName = `Court of Favours ${run}`;
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;

  // Wren is built through the API, with Celerity 2, and joins the troupe.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Wren" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
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
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});
  const asked = await send("POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  const accepted = await lead.page.request.post(`/api/approvals/${asked.id}/approve`, { headers, data: {} });
  expect(accepted.status(), await accepted.text()).toBe(200);

  // An elder power needs all five dots of its discipline: greyed in the Add panel, with a way to ask staff.
  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  await part("Disciplines").getByRole("button", { name: "Add" }).click();
  await p.getByRole("navigation", { name: "Categories" }).getByRole("button", { name: /^Elder Disciplines/ }).click();
  await p.getByLabel("Search Elder Disciplines").fill("Celerity: Zephyr");
  // Left out of what Wren can take: shown greyed, with the reason, a tap away.
  await expect(p.getByText("None you can take. 1 you can't:")).toBeVisible();
  await p.getByRole("button", { name: "show", exact: true }).click();
  const row = p.getByRole("listitem").filter({ has: p.getByRole("button", { name: /^Celerity: Zephyr/ }) });
  await expect(row.getByRole("button", { name: /^Celerity: Zephyr/ })).toBeDisabled();
  await expect(row).toContainText("An elder power needs all 5 dots of its discipline first.");
  await row.getByRole("button", { name: "Ask staff" }).click();
  const ask = p.getByRole("form", { name: "Ask staff for Celerity: Zephyr" });
  await ask.getByLabel("Why").fill("A gift of the Methuselah's blood");
  await ask.getByLabel("Ask for it at no XP cost").check();
  await ask.getByRole("button", { name: "Put it in the cart" }).click();

  // In the cart it is an exception line, with the rule it breaks, and nothing to pay.
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  const line = cart.getByRole("listitem").filter({ hasText: "Add Celerity: Zephyr" });
  await expect(line.getByText("exception", { exact: true })).toBeVisible();
  await expect(line.getByText("needs approval")).toBeVisible();
  await expect(line).toContainText("Asked of staff, free: A gift of the Methuselah's blood");
  await expect(line).toContainText("Against the rules: An elder power needs all 5 dots of its discipline first.");
  await p.screenshot(shots("exception-cart"));
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Some of it waits for the home troupe's approval.")).toBeVisible();
  await expect(part("Disciplines").getByRole("button", { name: "exception asked" })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Against the rules" })).toHaveCount(0);

  // The lead finds it among the exceptions, with the rule broken and the reason, and approves it.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/approvals`);
  await l.getByLabel("Kind").selectOption({ label: "Exceptions" });
  const card = l.locator("section").filter({ hasText: "Wren" });
  await expect(card.getByText("exception, free")).toBeVisible();
  await expect(card).toContainText("Celerity: Zephyr 0 → 1, asked for free");
  await expect(card).toContainText("Against the rules: An elder power needs all 5 dots of its discipline first.");
  await expect(card).toContainText("A gift of the Methuselah's blood");
  await l.screenshot(shots("exception-approval"));
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();

  // On Wren's sheet it is marked as given by exception, and its rule is not flagged.
  await p.reload();
  await expect(part("Disciplines").getByRole("button", { name: "by exception" })).toBeVisible();
  const exceptions = p.getByRole("list", { name: "Traits held by exception" });
  await expect(exceptions).toContainText("Celerity: Zephyr 1");
  await expect(exceptions).toContainText("Given by exception: approved by exc-lead");
  await expect(exceptions).toContainText(", free");
  await expect(p.getByRole("heading", { name: "Against the rules" })).toHaveCount(0);
  await part("Disciplines").getByRole("button", { name: "by exception" }).click();
  await expect(part("Disciplines")).toContainText("A gift of the Methuselah's blood");
  await p.screenshot(shots("exception-sheet"));

  // The lead gives Wren Calm Heart, which no Brujah may take: free, and despite that rule once it is shown.
  await l.goto(`/characters/${id}`);
  const merits = l.locator("section").filter({ has: l.getByRole("heading", { name: "Merits and Flaws", exact: true }) });
  await merits.getByRole("button", { name: "Give Merits and Flaws" }).click();
  await l.getByLabel("Search Merits to give").fill("Calm Heart");
  await l.getByRole("button", { name: /^Calm Heart/ }).click();
  const giving = l.getByRole("form", { name: "Give Calm Heart" });
  await giving.getByLabel("Free: at no XP cost").check();
  await giving.getByLabel("Reason").fill("Raised by a True Brujah");
  await giving.getByRole("button", { name: "Check" }).click();
  await expect(giving).toContainText("Brujah cannot take Calm Heart");
  await expect(giving.getByRole("button", { name: "Give", exact: true })).toBeDisabled();
  await giving.getByLabel("Give it despite these rules").check();
  await giving.getByRole("button", { name: "Give", exact: true }).click();
  await expect(merits.getByRole("button", { name: "by exception" })).toBeVisible();
  await expect(l.getByRole("list", { name: "Traits held by exception" })).toContainText("Given by exception: given by exc-lead");

  // Wren's player is told.
  await p.goto("/");
  await p.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(p.getByText("exc-lead gave Wren Calm Heart 1, free: Raised by a True Brujah")).toBeVisible();
});

test("a player says they committed diablerie, staff approve it, and then record another", async ({ browser }) => {
  const custodian = await person(browser, "dia-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "dia-lead");
  const player = await person(browser, "dia-player");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Sorrows ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;

  // Sable is built through the API and accepted at Generation 1.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Sable" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
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
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});
  const asked = await send("POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  const accepted = await lead.page.request.post(`/api/approvals/${asked.id}/approve`, { headers, data: {} });
  expect(accepted.status(), await accepted.text()).toBe(200);
  const held = async (name: string) => (await (await p.request.get(`/api/characters/${id}/sheet`)).json()).traits.find((t: { name: string }) => t.name === name).rating;

  // The troupe's setting for a Lesser Generation holder starts at leaving the flaw.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/rules/starting`);
  await expect(l.getByText("Leave the flaw.")).toBeVisible();

  // The player asks, with the date and a note.
  await p.goto(`/characters/${id}`);
  await p.getByRole("button", { name: "Ask staff: I committed diablerie" }).click();
  const ask = p.getByRole("form", { name: "Ask staff about diablerie" });
  await ask.getByLabel("Date").fill("2026-10-24");
  await ask.getByLabel("Note").fill("Drank my sire at Elysium");
  await ask.getByRole("button", { name: "Ask staff", exact: true }).click();
  await expect(p.getByText("You said Sable committed diablerie.")).toBeVisible();
  expect(await held("Generation")).toBe(1);

  // The lead sees what approving does, changes the Beast traits, and approves.
  await l.goto(`/troupes/${troupeId}/approvals`);
  await l.getByLabel("Kind").selectOption({ label: "Diablerie" });
  const card = l.locator("section").filter({ hasText: "Sable" });
  await expect(card).toContainText("committed diablerie on 24 Oct 2026");
  await expect(card).toContainText("Generation 1 → 2, as a free dot. Earlier buys keep what they cost.");
  await expect(card).toContainText("Humanity goes down 1");
  await card.getByLabel("Beast traits at the next game").fill("2");
  await card.getByLabel("Who was diablerized").fill("Her sire");
  await l.screenshot(shots("diablerie-approval"));
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();

  // Generation went up free, Humanity fell, and the date shows on the sheet and the printed sheet.
  expect(await held("Generation")).toBe(2);
  expect(await held("Humanity")).toBe(4);
  await p.reload();
  await expect(p.getByRole("list", { name: "Diablerie" })).toContainText("Diablerie: 24 Oct 2026");
  await expect(p.getByRole("list", { name: "Diablerie" })).not.toContainText("Her sire");
  await p.screenshot(shots("diablerie-sheet"));
  await p.goto(`/print/characters/${id}`);
  await expect(p.getByText("Diablerie: 24 Oct 2026")).toBeVisible();
  // Two Beast traits wait for the next game on the Play View.
  expect((await (await p.request.get(`/api/characters/${id}/play`)).json()).beast.value).toBe(2);

  // The lead records another from the character's page, and takes more Humanity than filled in.
  await l.goto(`/characters/${id}`);
  await expect(l.getByRole("list", { name: "Diablerie" })).toContainText("Her sire");
  await l.getByRole("button", { name: "Record diablerie" }).click();
  const form = l.getByRole("form", { name: "Record diablerie" });
  await form.getByLabel("Date").fill("2026-10-25");
  await form.getByLabel("Who was diablerized").fill("The Prince");
  await expect(form).toContainText("Generation 2 → 3, as a free dot.");
  await form.getByLabel("Humanity lowered by").fill("2");
  await expect(form).toContainText("Humanity goes down 2, with no XP back.");
  await form.getByRole("button", { name: "Record diablerie" }).click();
  await expect(l.getByRole("list", { name: "Diablerie" })).toContainText("Diablerie: 25 Oct 2026");
  expect(await held("Generation")).toBe(3);
  expect(await held("Humanity")).toBe(2);
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

test("Derangement traits on the Play View: a temporary derangement added, warnings to the edge, kept through Reset, and removed", async ({ browser }) => {
  const custodian = await person(browser, "derange-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "derange-lead");
  const troupeName = `Court of Bedlam ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Two NPCs the lead runs, neither with the Derangement flaw: a Malkavian, whose
  // clan weakness is a derangement, and a Toreador.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const npc = async (name: string, clan: string) => {
    const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(made.status(), await made.text()).toBe(201);
    const id: string = (await made.json()).id;
    const rated = await p.request.put(`/api/characters/${id}/npc/ratings`, { headers, data: { category: "clan", name: clan, rating: null, detail: "" } });
    expect(rated.status(), await rated.text()).toBe(200);
    return id;
  };
  const ophelia = await npc("Ophelia", "Malkavian");
  const lucien = await npc("Lucien", "Toreador");

  // No Derangement flaw on the sheet: no tracker, only a way to add one.
  await p.goto(`/play/characters/${lucien}`);
  await expect(p.getByLabel("Blood: 10 of 10")).toBeVisible();
  await expect(p.getByRole("heading", { name: "Derangement traits" })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Add a temporary derangement…" })).toBeVisible();

  // The Malkavian's clan derangement is added by hand, as a temporary one.
  await p.goto(`/play/characters/${ophelia}`);
  await p.getByLabel("Quick notes").uncheck();
  await expect(p.getByRole("heading", { name: "Derangement traits" })).toHaveCount(0);
  await p.getByRole("button", { name: "Add a temporary derangement…" }).click();
  const adding = p.getByRole("dialog", { name: "Temporary derangement" });
  await adding.getByLabel("Derangement").fill("Paranoia: the Prince");
  await adding.getByLabel("Where it came from (optional)").fill("Malkavian clan weakness");
  await adding.getByRole("button", { name: "Add" }).click();
  await expect(p.getByText("Temporary derangement added: Paranoia: the Prince, from Malkavian clan weakness")).toBeVisible();

  // A Malkavian always has 1, so it can't be removed.
  const traits = p.getByRole("region", { name: "Derangement traits" });
  await expect(traits.getByLabel("Derangement traits: 1 of 3")).toBeVisible();
  await expect(traits).toContainText("Malkavians always have 1.");
  await expect(traits.getByRole("listitem").filter({ hasText: "Paranoia: the Prince" })).toContainText("Temporary, from Malkavian clan weakness");
  await expect(traits.getByRole("button", { name: "Remove a Derangement trait", exact: true }).last()).toBeDisabled();
  await expect(traits.getByRole("button", { name: "Severe response" })).toBeDisabled();

  // Two triggers resisted: a warning at 2, and at 3 how a psychotic break plays out.
  const mark = traits.getByRole("button", { name: "Mark a Derangement trait", exact: true }).last();
  await mark.click();
  await expect(traits.getByRole("note", { name: "One trait from the edge" })).toContainText("MET: VtM core, p. 267");
  await mark.click();
  await expect(traits.getByLabel("Derangement traits: 3 of 3")).toBeVisible();
  const edge = traits.getByRole("note", { name: "On the edge of a psychotic break" });
  await expect(edge).toContainText("A severe response lasts five minutes.");
  await expect(edge).toContainText("to 1, as a Malkavian always keeps 1");
  // A warning only: the tap goes through, and nothing is blocked.
  await expect(p.getByText("Derangement traits 2 → 3")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await p.screenshot(shots("play-derangements"));
  // Undo takes one back, as any tap.
  await p.getByRole("button", { name: "Undo Derangement traits 2 → 3" }).click();
  await expect(p.getByText("Undid: Derangement traits 2 → 3")).toBeVisible();
  await expect(traits.getByLabel("Derangement traits: 2 of 3")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // Another device (the custodian's) sees the same.
  const other = custodian.page;
  await other.goto(`/play/characters/${ophelia}`);
  await expect(other.getByLabel("Derangement traits: 2 of 3")).toBeVisible();
  await expect(other.getByText("Paranoia: the Prince", { exact: true })).toBeVisible();

  // Reset for the next game puts Blood back but leaves Derangement traits and the derangement.
  await p.getByRole("button", { name: "Spend Blood", exact: true }).last().click();
  await expect(p.getByLabel("Blood: 9 of 10")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await p.getByRole("button", { name: "Reset for next game…" }).click();
  await expect(p.getByText("Derangement traits stay at 2.")).toBeVisible();
  await p.getByRole("button", { name: "Reset for next game", exact: true }).click();
  await expect(p.getByText("Game 2")).toBeVisible();
  await expect(p.getByLabel("Blood: 10 of 10")).toBeVisible();
  await expect(traits.getByLabel("Derangement traits: 2 of 3")).toBeVisible();
  await p.reload();
  await expect(traits.getByLabel("Derangement traits: 2 of 3")).toBeVisible();
  await expect(traits.getByText("Paranoia: the Prince", { exact: true })).toBeVisible();

  // A severe response clears them, down to the Malkavian's 1.
  await traits.getByRole("button", { name: "Severe response" }).click();
  await expect(traits.getByLabel("Derangement traits: 1 of 3")).toBeVisible();
  await expect(p.getByText("Derangement traits 2 → 1")).toBeVisible();
  await expect(p.getByText("“Severe response”")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await other.reload();
  await expect(other.getByLabel("Derangement traits: 1 of 3")).toBeVisible();

  // Removed by the player when it's over: the tracker goes, back to a way to add one.
  await traits.getByRole("button", { name: "Remove Paranoia: the Prince" }).click();
  await expect(p.getByText("Temporary derangement removed: Paranoia: the Prince, from Malkavian clan weakness")).toBeVisible();
  await expect(p.getByRole("heading", { name: "Derangement traits" })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Add a temporary derangement…" })).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");
  await other.reload();
  await expect(other.getByRole("heading", { name: "Derangement traits" })).toHaveCount(0);
});

test("Beast traits on the Play View warn what each one brings, and the Frenzy rules open on request", async ({ browser }) => {
  const custodian = await person(browser, "frenzy-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "frenzy-lead");
  const troupeName = `Court of Fangs ${run}`;
  await custodian.page.reload();
  await custodian.page.getByRole("link", { name: "Troupes" }).click();
  await expect(custodian.page.getByRole("heading", { name: "New troupe" })).toBeVisible();
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // A Brujah NPC the lead runs at game.
  const p = lead.page;
  await p.getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name: "Tobias", wizard: false } });
  expect(made.status(), await made.text()).toBe(201);
  const npc = (await made.json()).id;
  const rated = await p.request.put(`/api/characters/${npc}/npc/ratings`, { headers, data: { category: "clan", name: "Brujah", rating: null, detail: "" } });
  expect(rated.status(), await rated.text()).toBe(200);

  await p.goto(`/play/characters/${npc}`);
  await expect(p.getByLabel("Beast traits: 0 of 5")).toBeVisible();
  await expect(p.getByRole("note")).toHaveCount(0);

  // Each Beast trait says what now makes a frenzy test, and how to play it.
  const gain = p.getByRole("button", { name: "Gain a Beast traits point" });
  await gain.click();
  const foothold = p.getByRole("note", { name: "The Beast has a foothold" });
  await expect(foothold).toContainText("You can frenzy now.");
  await expect(foothold).toContainText("against 11");
  await expect(foothold).toContainText("MET: VtM core, pp. 301–302; Vol. II Issue 1 update, pp. 97–98");
  await gain.click();
  await expect(p.getByRole("note", { name: "The Beast is awake" })).toContainText("a single blow of 3 or more damage (rage)");
  await gain.click();
  await gain.click();
  await expect(p.getByLabel("Beast traits: 4 of 5")).toBeVisible();
  await expect(p.getByRole("note", { name: "One trait from losing Humanity" })).toContainText("One more Beast trait costs a dot of permanent Humanity.");
  // A warning only: the fifth goes through.
  await gain.click();
  await expect(p.getByLabel("Beast traits: 5 of 5")).toBeVisible();
  await expect(p.getByRole("note", { name: "A dot of Humanity is lost" })).toBeVisible();
  await expect(p.getByText("Beast traits 4 → 5")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  // The Frenzy rules, closed until asked for.
  const frenzy = p.getByRole("button", { name: /^Frenzy/ });
  await expect(frenzy).toHaveAttribute("aria-expanded", "false");
  await expect(p.getByText("Riding the wave")).toHaveCount(0);
  await frenzy.click();
  await expect(frenzy).toHaveAttribute("aria-expanded", "true");
  await expect(p.getByRole("heading", { name: /Riding the wave/ })).toBeVisible();
  await expect(p.getByText("Fear ends once you've escaped and hidden quietly for 10 minutes.", { exact: false })).toBeVisible();
  await p.screenshot(shots("play-frenzy"));
  await frenzy.click();
  await expect(frenzy).toHaveAttribute("aria-expanded", "false");
  await expect(p.getByText("Riding the wave")).toHaveCount(0);
});

test("a coterie's shared Haven: staff set it up, a player logs a use, and the other sharer reads it in the log", async ({ browser }) => {
  const custodian = await person(browser, "share-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "share-lead");
  const first = await person(browser, "share-first");
  const second = await person(browser, "share-second");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Shared Roof ${run}`, lead_handle: lead.handle });

  // Agnes and Bram, both at home in the troupe.
  const build = async (page: Page, name: string) => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Haven", 2], ["Generation", 1]],
      disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
    };
    for (const [category, list] of Object.entries(picks))
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`);
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id as string;
  };
  const agnes = await build(first.page, "Agnes");
  const bram = await build(second.page, "Bram");

  // The lead sets up the coterie's Haven: Agnes puts in 2 dots, Bram 1.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}`);
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: "Shared backgrounds" }).click();
  await l.getByRole("button", { name: "Set up a shared background" }).click();
  const setUp = l.getByRole("form", { name: "Set up a shared background" });
  await setUp.getByLabel("Name").fill("The coterie's Haven");
  await expect(setUp.getByLabel("Background")).toHaveValue("Haven");
  await setUp.getByLabel("What it gives (optional)").fill("Security, Guards");
  await setUp.getByLabel("Character 1", { exact: true }).selectOption({ label: "Agnes" });
  await setUp.getByLabel("Dots 1", { exact: true }).fill("2");
  await setUp.getByRole("button", { name: "Add a character" }).click();
  await setUp.getByLabel("Character 2", { exact: true }).selectOption({ label: "Bram" });
  await setUp.getByRole("button", { name: "Set up" }).click();
  await expect(l.getByRole("heading", { name: "The coterie's Haven" })).toBeVisible();
  await expect(l.getByText("3 of 5 dots")).toBeVisible();
  await expect(l.getByLabel("Sharing it")).toHaveText("Sharing it: Agnes 2 dots, Bram 1 dot.");
  await expect(l.getByText(/A record only: nothing logged here changes a rating/)).toBeVisible();

  // Agnes's player finds it on her page, and logs drawing on it.
  const a = first.page;
  await a.goto(`/characters/${agnes}`);
  await a.locator("main").getByRole("link", { name: "Shared backgrounds" }).click();
  await expect(a.getByRole("heading", { name: "The coterie's Haven" })).toBeVisible();
  await expect(a.getByRole("button", { name: "Log dots" })).toHaveCount(0);
  await a.getByRole("button", { name: "Log a use" }).click();
  const use = a.getByRole("form", { name: "Log a use" });
  await expect(use.getByLabel("Who drew on it")).toHaveValue(agnes);
  await use.getByLabel("What for").fill("Hiding from the hunters for the day");
  await use.getByRole("button", { name: "Log use" }).click();
  const log = a.getByRole("list", { name: "The coterie's Haven log" });
  await expect(log.getByRole("listitem").first()).toContainText("Agnes drew on it");
  await expect(log.getByRole("listitem").first()).toContainText("Hiding from the hunters for the day");
  await a.screenshot(shots("shared-background"));

  // Bram's player reads it in the same log, but cannot take Agnes's use off it.
  const b = second.page;
  await b.goto(`/characters/${bram}/shared`);
  const his = b.getByRole("list", { name: "The coterie's Haven log" });
  await expect(his.getByRole("listitem").first()).toContainText("Hiding from the hunters for the day");
  await expect(his.getByRole("listitem").first()).toContainText("logged by share-first");
  await expect(his.getByRole("listitem").first().getByRole("button", { name: "Delete" })).toHaveCount(0);

  // The lead logs Bram taking his dot out; the total follows the log.
  await l.reload();
  await expect(l.getByRole("list", { name: "The coterie's Haven log" }).getByRole("listitem").first()).toContainText("Agnes drew on it");
  await l.getByRole("button", { name: "Log dots" }).click();
  const dots = l.getByRole("form", { name: "Log dots" });
  await dots.getByLabel("Dots", { exact: true }).selectOption("Taken out");
  await dots.getByLabel("Who").selectOption({ label: "Bram (1 dot)" });
  await dots.getByLabel("Note (optional)").fill("Left the coterie");
  await dots.getByRole("button", { name: "Log dots" }).click();
  await expect(l.getByText("2 of 5 dots")).toBeVisible();
  await expect(l.getByLabel("Sharing it")).toHaveText("Sharing it: Agnes 2 dots. Took their dots out: Bram.");
});

test("a skill's specialisations sit in its own list item, in the sheet's two columns and on a phone", async ({ browser }) => {
  const { page: p } = await person(browser, "stay-together");
  const id = await builtVampire(p, "Marguerite", "Toreador", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Auspex", 2], ["Celerity", 1], ["Presence", 1]],
    skills: ATTRIBUTES_AND_FOCUSES.skills.map(([name, rating]) => [name === "Medicine" ? "Academics" : name, rating]),
  });
  await p.goto(`/characters/${id}`);
  const skills = p.locator("section").filter({ has: p.getByRole("heading", { name: "Skills", exact: true }) });
  const academics = skills.locator("li[data-trait='Academics']");
  for (const width of [1280, 390]) {
    await p.setViewportSize({ width, height: 900 });
    // Name one specialisation for Academics.
    if (width === 1280) {
      await academics.getByRole("button", { name: "Add to Academics Specializations" }).click();
      await academics.getByLabel("Name a Academics Specializations").fill("Medieval");
      await academics.getByRole("button", { name: "Add", exact: true }).click();
    }
    // The skill, its specialisations and their Add button all sit in the one item.
    await expect(academics.getByText("Academics", { exact: true }).first()).toBeVisible();
    await expect(academics.getByText("Academics Specializations 1/1")).toBeVisible();
    await expect(academics.getByRole("button", { name: "Remove Medieval" })).toBeVisible();
    await expect(academics.getByRole("listitem")).toHaveCount(0); // one item for the whole trait
    // And the item is kept whole across a column break.
    await expect(academics).toHaveCSS("break-inside", "avoid");
  }
  await p.screenshot(shots("specializations-stay-together"));
});

test("an attribute stops rising at the limit Generation gives", async ({ browser }) => {
  const { page: p } = await person(browser, "limit-player");
  // A Neonate may take one attribute to 11 (core p. 102).
  const id = await builtVampire(
    p,
    "Stoddard",
    "Brujah",
    { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Generation", 1], ["Herd", 2], ["Fame", 3]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] },
    [["attributes", "Physical", 10]],
  );
  await p.goto(`/characters/${id}`);
  const cart = p.getByRole("list", { name: "Changes in the cart" });

  // One dot to 11 is fine for a Neonate; the next is refused on its line, and nothing can be spent.
  await p.getByRole("button", { name: "Raise Physical" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Physical 10 → 11" })).not.toContainText("Generation rating");
  await expect(p.getByRole("button", { name: "Spend XP" })).toBeEnabled();
  await p.getByRole("button", { name: "Raise Physical" }).click();
  await expect(cart.getByRole("listitem").filter({ hasText: "Physical 10 → 12" })).toContainText("only as many dots, in all, as the Generation rating");
  await expect(p.getByRole("button", { name: "Spend XP" })).toBeDisabled();
  // Stepping back to 11 makes it fine again.
  await p.getByRole("button", { name: "Lower Physical" }).click();
  await expect(p.getByRole("button", { name: "Spend XP" })).toBeEnabled();
});

test("a player says who each Retainer bought is, and a storyteller links one to an NPC", async ({ browser }) => {
  const custodian = await person(browser, "ret-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "ret-lead");
  const owner = await person(browser, "ret-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Retinue Row ${run}`, lead_handle: lead.handle });

  // Dorothea, at home in the troupe with Marta as a Retainer at 3, and staff give her Pike at 1.
  const { id } = await send(owner.page, "POST", "/api/characters", { splat: "vampire", name: "Dorothea" });
  await send(owner.page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const picks: Record<string, [string, number, string?][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Retainers", 3, "Marta, the driver"], ["Haven", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, list] of Object.entries(picks))
    await send(owner.page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating, detail]) => ({ name: n, rating, detail: detail ?? "" })) });
  await send(owner.page, "POST", `/api/characters/${id}/creation/complete`);
  const asked = await send(owner.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  await send(lead.page, "POST", `/api/characters/${id}/give`, { category: "backgrounds", name: "Retainers", detail: "Pike", rating: 1, free: true, reason: "A second Retainer" });
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Marta Voss", wizard: false });

  // Both are listed, under the last of them, with the dots bought for each.
  const p = owner.page;
  await p.goto(`/characters/${id}`);
  const list = p.getByLabel("Retainers list");
  await expect(list).toHaveCount(1);
  await expect(list.getByRole("list", { name: "Retainers" }).getByRole("listitem")).toHaveCount(2);
  // The player says who Marta is; her name and dots are the sheet's.
  await list.getByRole("button", { name: "Edit Retainers" }).click();
  await expect(list.getByLabel("Retainer name")).toHaveCount(0);
  await list.getByLabel("About Marta, the driver").fill("Drives at night");
  await list.getByRole("button", { name: "Save Retainers" }).click();
  await expect(list.getByText("Drives at night")).toBeVisible();
  await expect(list.getByRole("button", { name: /^NPC for/ })).toHaveCount(0);
  await p.screenshot(shots("retainers"));

  // Both show on the printed sheet and the Play View.
  await p.goto(`/print/characters/${id}`);
  await expect(p.getByRole("article", { name: "Retainer: Marta, the driver" })).toContainText("Drives at night");
  await expect(p.getByRole("article", { name: "Retainer: Pike" })).toContainText("Pool 2");
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Sheet" }).click();
  const playing = p.getByRole("list", { name: "Retainers" });
  await expect(playing.getByText("Marta, the driver")).toBeVisible();
  await expect(playing.getByText("Pike")).toBeVisible();

  // A storyteller links Marta to the NPC, and the link opens it.
  const l = lead.page;
  await l.goto(`/characters/${id}`);
  const his = l.getByLabel("Retainers list");
  await his.getByRole("button", { name: "Edit Retainers" }).click();
  await his.getByLabel("NPC for Marta, the driver").selectOption({ label: "Marta Voss" });
  await his.getByRole("button", { name: "Save Retainers" }).click();
  await his.getByRole("link", { name: "Marta Voss" }).click();
  await expect(l.getByRole("heading", { name: "Marta Voss" }).first()).toBeVisible();

  // The change is on the character's log.
  await l.goto(`/characters/${id}/log`);
  await expect(l.getByText("ret-lead linked Marta, the driver, one of Dorothea (ret-player)'s Retainers, to an NPC.")).toBeVisible();

  // Pike is killed: the sheet says when his dot comes back (a game, and two
  // weeks), and his block on the Play View is greyed out until then.
  await p.goto(`/characters/${id}`);
  await list.getByRole("button", { name: "Edit Retainers" }).click();
  await list.getByLabel("Status of Pike").selectOption("killed");
  await list.getByRole("button", { name: "Save Retainers" }).click();
  await expect(list.getByText(/^Its dots come back once 1 game has gone by since, and not before /)).toBeVisible();
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Tracker" }).click();
  const pike = p.getByRole("article", { name: "Retainer: Pike" });
  await expect(pike).toHaveAttribute("aria-disabled", "true");
  await expect(pike.getByRole("status")).toContainText("Killed");
  await expect(pike.getByRole("button", { name: "Spend Pike: health" })).toBeDisabled();
  await expect(p.getByRole("article", { name: "Retainer: Marta, the driver" }).getByRole("button", { name: "Spend Marta, the driver: health" })).toBeEnabled();
});

test("in the cart, a second Retainer and a second Alternate Identity are each bought on their own, by name", async ({ browser }) => {
  const { page: p } = await person(browser, "twofold-player");
  const headers = { "X-Horatio": "1" };
  const send = async (method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await p.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  // Ysolde starts with Bocephus as a Retainer at 3 and one cover identity at 2, at Generation 1.
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Ysolde" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Nosferatu", rating: null });
  const picks: Record<string, [string, number, string?][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Stealth", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Retainers", 3, "Bocephus"], ["Alternate Identity", 2, "Dr. Ellen Marsh, coroner"], ["Generation", 1]],
    disciplines: [["Animalism", 2], ["Obfuscate", 1], ["Potence", 1]],
  };
  for (const [category, list] of Object.entries(picks))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating, detail]) => ({ name: n, rating, detail: detail ?? "" })) });
  await send("POST", `/api/characters/${id}/creation/complete`);

  await p.goto(`/characters/${id}`);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  // A second Retainer is named as it goes in, and priced from its own first dot: 1 + 2 at Generation 1.
  await part("Backgrounds").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Backgrounds").fill("Retainers");
  await p.getByRole("button", { name: "Retainers" }).first().click();
  await expect(p.getByText("Each Retainer is bought on its own, with its own dots, up to 5.")).toBeVisible();
  await p.getByPlaceholder("Such as Bocephus").fill("Rook");
  await p.getByLabel("Rating").fill("2");
  await p.getByRole("button", { name: "Add to cart" }).click();
  await expect(cart.getByText("Add Retainers: Rook 2 · 3 XP")).toBeVisible();
  // And a second identity, by its own name.
  await part("Backgrounds").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Backgrounds").fill("Alternate");
  await p.getByRole("button", { name: "Alternate Identity" }).first().click();
  await p.getByPlaceholder("Such as Dr. Ellen Marsh, coroner").fill("Father Kell");
  await p.getByRole("button", { name: "Add to cart" }).click();
  await expect(cart.getByText("Add Alternate Identity: Father Kell 1 · 1 XP")).toBeVisible();
  // Bocephus's fourth dot costs his own next dot, though it is the sixth Retainer dot in all.
  await p.getByRole("button", { name: "Raise Retainers: Bocephus" }).click();
  await expect(cart.getByText("Retainers: Bocephus 3 → 4 · 4 XP")).toBeVisible();
  await p.getByRole("button", { name: "Spend XP" }).click();
  await expect(p.getByText("Spent 8 XP.")).toBeVisible();

  // Each is on the sheet by name, with its own dots.
  const backgrounds = part("Backgrounds");
  for (const name of ["Retainers: Bocephus", "Retainers: Rook", "Alternate Identity: Dr. Ellen Marsh, coroner", "Alternate Identity: Father Kell"])
    await expect(backgrounds.getByRole("button", { name: `Raise ${name}`, exact: true })).toBeVisible();
  await expect(p.getByLabel("Retainers list").getByRole("listitem")).toHaveCount(2);

  // Bocephus is a ghoul, with three skills and Obfuscate as his specialties (p. 105).
  const list = p.getByLabel("Retainers list");
  await list.getByRole("button", { name: "Edit Retainers" }).click();
  await list.getByLabel("Bocephus is a ghoul").check();
  for (const skill of ["Brawl", "Stealth", "Dodge"]) await list.getByLabel("Add a specialty for Bocephus").selectOption(skill);
  await list.getByLabel("Discipline for Bocephus").selectOption("Obfuscate");
  await expect(list.getByText("Specialties 4 of 4:")).toBeVisible();
  await list.getByRole("button", { name: "Save Retainers" }).click();
  await expect(list.getByText("Brawl, Stealth, Dodge, Obfuscate")).toBeVisible();
  // Father Kell is Accepted by the Sabbat; each identity says what its rating stands up to.
  await p.getByRole("button", { name: "Accepted by a sect or group?" }).last().click();
  await p.getByLabel("Who Accepts Father Kell").fill("the Sabbat");
  await p.getByRole("button", { name: "Save", exact: true }).click();
  await expect(p.getByLabel("About Father Kell")).toContainText("Accepted by the Sabbat.");
  await expect(p.getByLabel("About Dr. Ellen Marsh, coroner")).toContainText("Well grounded");

  // On the Play View, each Retainer has a pool of its own, and its health and Blood to tap.
  await p.goto(`/play/characters/${id}`);
  await p.getByRole("tab", { name: "Tracker" }).click();
  const bocephus = p.getByRole("article", { name: "Retainer: Bocephus" });
  const rook = p.getByRole("article", { name: "Retainer: Rook" });
  await expect(bocephus.getByLabel("Bocephus's pool: 8")).toBeVisible();
  await expect(rook.getByLabel("Rook's pool: 4")).toBeVisible();
  await expect(bocephus.getByRole("listitem").filter({ hasText: "Brawl" })).toContainText("13");
  await expect(bocephus.getByText("4. Vanish From the Mind's Eye")).toBeVisible();
  await expect(bocephus.getByText("Cloak the Gathering")).toHaveCount(0);
  await expect(rook.getByText("Blood")).toHaveCount(0);
  await p.getByRole("checkbox", { name: "Quick notes" }).uncheck();
  await bocephus.getByRole("button", { name: "Spend Bocephus: Blood" }).click();
  await expect(bocephus.getByLabel("Bocephus: Blood: 4 of 5")).toBeVisible();
  await rook.getByRole("button", { name: "Spend Rook: health" }).click();
  await expect(rook.getByLabel("Rook: health: 1 of 2")).toBeVisible();

  // And on the Sheet tab, both identities by name, with who Accepts one.
  await p.getByRole("tab", { name: "Sheet" }).click();
  await expect(p.getByText("Alternate Identity: Dr. Ellen Marsh, coroner")).toBeVisible();
  await expect(p.getByText("Alternate Identity: Father Kell")).toBeVisible();
  await expect(p.getByText("Accepted by the Sabbat.")).toBeVisible();
});

test("a page whose file is gone after a deploy reloads once, then says Horatio was updated", async ({ browser }) => {
  const { page } = await person(browser, "Staleo");
  let asked = 0;
  await page.route("**/assets/AccountPage-*.js", (route) => {
    asked += 1;
    return route.fulfill({ status: 404, contentType: "text/plain", body: "not found" });
  });
  await page.goto("/characters");
  await page.getByTitle("Your account").click();
  await expect(page.getByText("Horatio has been updated. Reload to continue.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Reload" })).toBeVisible();
  // One reload was tried, and no more: two asks for the file, not a loop.
  expect(asked).toBeGreaterThan(0);
  expect(asked).toBeLessThanOrEqual(3);
});
