import { execFileSync } from "node:child_process";
import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * One troupe's month, end to end: the custodian sets up a troupe, a player
 * builds a character and brings it to the troupe, the lead approves it and runs
 * a downtime cycle, a narrator answers an action, and the player reads the
 * results. Each person is a separate browser session.
 */

const run = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
const PASSWORD = "a long enough password";
const shots = (name: string) => ({ path: `test-results/screens/${test.info().project.name}-${name}.png`, fullPage: true });

async function person(browser: Browser, name: string): Promise<{ page: Page; email: string; handle: string }> {
  const page = await (await browser.newContext()).newPage();
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
  await expect(lead.page.getByRole("heading", { name: "Add or change staff" })).toBeVisible();
  await lead.page.screenshot(shots("troupe-nav"));
  // Found by typing part of their handle, and picked from what comes up.
  await lead.page.getByLabel("Handle").fill(narrator.handle.slice(0, -3));
  await lead.page.getByRole("option", { name: `@${narrator.handle}` }).click();
  await expect(lead.page.getByLabel("Handle")).toHaveValue(narrator.handle);
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
  const next = async (heading: string) => {
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible();
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
  await part("Backgrounds").getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Search Backgrounds").fill("Elite");
  await p.getByRole("button", { name: "Influences: The Elite" }).click();
  await p.getByRole("button", { name: "Buy" }).click();
  await expect(p.getByText("29", { exact: true })).toBeVisible(); // 30 − 1 for Influence
  // A focus can be changed after creation, for 10 XP.
  await p.getByRole("listitem").filter({ hasText: "Strength" }).getByRole("button", { name: "Change" }).click();
  await p.getByLabel("Change Strength to").selectOption("Dexterity");
  await p.getByRole("button", { name: "10 XP" }).click();
  await expect(p.getByText("19", { exact: true })).toBeVisible();
  // Merits that give other traits apply them: Rugged adds a health level to each track.
  await part("Merits and Flaws").getByRole("button", { name: "Add" }).click();
  // Every Ventrue merit, though Agnes is Brujah and cannot take them.
  await p.getByLabel("Show").selectOption({ label: "For Ventrue" });
  await expect(p.getByRole("button", { name: /Aura of Command/ })).toBeDisabled();
  await p.getByLabel("Show").selectOption({ label: "What this character can take" });
  await p.getByLabel("Search Merits").fill("Rugged");
  await p.getByRole("button", { name: /^Rugged/ }).click();
  await p.getByRole("button", { name: "Buy" }).click();
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
  await lead.page.getByRole("link", { name: "People", exact: true }).click();
  await lead.page.locator("main").getByRole("link", { name: "Characters", exact: true }).click();
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

  // Once accepted, a discipline dot waits on the home troupe, with the XP held.
  await p.locator("main").getByRole("link", { name: "Sheet", exact: true }).click();
  await p.getByRole("button", { name: "Raise Celerity" }).click();
  await expect(p.getByText("awaiting approval").first()).toBeVisible();
  await lead.page.getByRole("link", { name: /Approvals/ }).click();
  await expect(lead.page.getByText(/Celerity 2 → 3, for 9 XP/)).toBeVisible();
  await lead.page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(lead.page.getByText("Nothing pending.")).toBeVisible();
  await p.reload();
  await expect(p.getByText("awaiting approval")).toHaveCount(0);

  // The troupe's characters and log show what happened.
  await lead.page.getByRole("link", { name: "People", exact: true }).click();
  await lead.page.locator("main").getByRole("link", { name: "Characters", exact: true }).click();
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
  // What came of it shows right under the trait, where the player is looking.
  const investigation = p.locator("li", { has: p.getByRole("button", { name: "Raise Investigation" }) });
  await expect(investigation.locator("xpath=following-sibling::li[1]")).toHaveText("Spent 1 XP.");
  await p.locator("main").getByRole("link", { name: "Log", exact: true }).click();
  await expect(p.getByText("raised Agnes's Investigation from 1 to 2 (1 XP).", { exact: false })).toBeVisible();

  // The troupe lists the areas its Elite influence covers; Agnes picks one.
  await lead.page.getByRole("link", { name: "Customize", exact: true }).click();
  await lead.page.getByRole("link", { name: "Specialisations", exact: true }).click();
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
  await p.getByRole("button", { name: "Buy" }).click();
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
  await p.screenshot(shots("downtime"));
  await p.getByRole("button", { name: "Submit downtime" }).click();
  await expect(p.getByText("submitted", { exact: true })).toBeVisible();

  // The lead hands the action to the narrator, who writes it.
  await lead.page.getByRole("link", { name: "Responses" }).click();
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
  await p.screenshot(shots("sheet-pips"));
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
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible();
  }
  await expect(p.getByText("0 of 9 points")).toBeVisible();
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
  await p.getByRole("link", { name: "People", exact: true }).click();
  await p.locator("main").getByRole("link", { name: "NPCs", exact: true }).click();
  await expect(p.getByRole("heading", { name: "New NPC" })).toBeVisible();
  await p.getByLabel("Name").fill("Prince Vasquez");
  await p.getByRole("button", { name: "Quick build" }).click();
  await expect(p.getByRole("heading", { name: "Prince Vasquez" })).toBeVisible();

  await p.getByLabel("Clan").selectOption("Ventrue");
  await expect(p.getByLabel("Clan")).toHaveValue("Ventrue");
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
  await p.getByRole("link", { name: "People", exact: true }).click();
  await p.locator("main").getByRole("link", { name: "Characters", exact: true }).click();
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
  // Uncommon disciplines are never offered; once three are chosen, nothing else is.
  await expect(page.getByRole("checkbox", { name: "Protean" })).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: "Dominate" })).toHaveCount(0);
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

  await p.getByRole("link", { name: "People", exact: true }).click();
  await p.locator("main").getByRole("link", { name: "Characters", exact: true }).click();
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
  await expect(p.getByText("visiting")).toBeVisible();
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
  // Quick notes start on: a spend asks what it was for, and the note is optional.
  await expect(p.getByLabel("Quick notes")).toBeChecked();
  await p.getByRole("button", { name: "Spend Blood", exact: true }).last().click();
  await p.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(p.getByLabel("Blood: 7 of 12")).toBeVisible();
  await expect(p.getByText("Blood 8 → 7")).toBeVisible();
  await expect(p.getByRole("status")).toHaveText("Saved");

  await p.getByLabel("Quick notes").uncheck();

  // The Pools tab, loaded once with the page: initiative with and without
  // Celerity, Dodge, and what each power does. The Sheet tab has the stats.
  await p.getByRole("tab", { name: "Pools" }).click();
  const initiative = p.getByRole("listitem").filter({ hasText: /^Initiative/ });
  await expect(initiative.getByText("5", { exact: true })).toBeVisible();
  await expect(initiative.getByText("With Celerity active")).toBeVisible();
  await expect(initiative.getByText("7", { exact: true })).toBeVisible();
  await expect(p.getByRole("listitem").filter({ hasText: /^Dodge/ }).getByText("7", { exact: true }).first()).toBeVisible();
  await expect(p.getByText("Alacrity", { exact: true })).toBeVisible();
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
  await page.getByRole("radiogroup", { name: "Send emails" }).getByRole("radio", { name: "Once a day" }).click();
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
  await page.getByRole("radiogroup", { name: "Text size" }).getByRole("radio", { name: "Large" }).click();
  // At once, with no reload, and still after one.
  await expect.poll(fontSize).not.toBe(normal);
  const large = await fontSize();
  expect(parseFloat(large) / parseFloat(normal)).toBeCloseTo(1.15);
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
