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

async function person(browser: Browser, name: string): Promise<{ page: Page; email: string }> {
  const page = await (await browser.newContext()).newPage();
  const email = `${name}-${run}@example.com`;
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your characters" })).toBeVisible();
  return { page, email };
}

function makeCustodian(email: string) {
  execFileSync("uv", ["run", "python", "-m", "horatio.custodian", email], { cwd: "../backend", stdio: "ignore" });
}

test("a troupe's month, from new character to downtime results", async ({ browser }) => {
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
  await custodian.page.getByLabel("Lead storyteller's email").fill(lead.email);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // The lead adds a narrator.
  await lead.page.getByRole("link", { name: "Troupes" }).click();
  await lead.page.getByRole("link", { name: troupeName }).click();
  await lead.page.getByRole("link", { name: "Staff" }).click();
  await expect(lead.page.getByRole("heading", { name: "Add or change staff" })).toBeVisible();
  await lead.page.getByLabel("Email").fill(narrator.email);
  await lead.page.getByRole("button", { name: "Save" }).click();
  await expect(lead.page.getByText("narrator · Narrator")).toBeVisible();

  // The player builds a character: creation picks, a clan, then Influence bought with XP.
  const p = player.page;
  await p.getByLabel("Name").fill("Agnes");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Agnes" })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Character creation" })).toBeVisible();
  const choose = async (category: string, trait: string, button: string) => {
    await p.getByLabel("Category").selectOption({ label: category });
    await p.getByLabel("Trait").selectOption(trait);
    await p.getByRole("button", { name: button }).click();
    await expect(p.locator("main").getByText(trait, { exact: true }).first()).toBeVisible();
  };
  // Picks go highest first, which is the pick the form offers first.
  for (const [category, trait] of [
    ["Attributes", "Physical"],
    ["Attributes", "Social"],
    ["Attributes", "Mental"],
    ["Physical Focus", "Strength"],
    ["Mental Focus", "Wits"],
    ["Social Focus", "Charisma"],
    ["Skills", "Brawl"],
    ["Skills", "Dodge"],
    ["Skills", "Athletics"],
    ["Skills", "Awareness"],
    ["Skills", "Empathy"],
    ["Skills", "Firearms"],
    ["Skills", "Investigation"],
    ["Skills", "Leadership"],
    ["Skills", "Medicine"],
    ["Skills", "Melee"],
    ["Backgrounds", "Fame"],
    ["Backgrounds", "Herd"],
    ["Backgrounds", "Allies"],
    ["Disciplines", "Celerity"],
    ["Disciplines", "Potence"],
    ["Disciplines", "Presence"],
  ] as const) {
    await choose(category, trait, "Place pick");
  }
  await p.screenshot(shots("creation"));
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Character creation" })).toBeHidden();
  await choose("Clan", "Brujah", "Choose");
  await p.getByLabel("Category").selectOption({ label: "Backgrounds" });
  await p.getByLabel("Trait").selectOption("Influences: The Elite");
  await p.getByRole("button", { name: "Buy" }).click();
  await expect(p.getByText("29", { exact: true })).toBeVisible(); // 30 − 1 for Influence
  await p.screenshot(shots("sheet"));

  // …and asks to make the troupe its home.
  await p.locator("main").getByRole("link", { name: "Troupes" }).click();
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: troupeName });
  await expect(p.getByText("Nothing differs")).toBeVisible();
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(/Waiting for .* storytellers/)).toBeVisible();

  // The lead approves it.
  await lead.page.getByRole("link", { name: "Approvals" }).click();
  await expect(lead.page.getByText("joining as home troupe")).toBeVisible();
  await lead.page.screenshot(shots("approvals"));
  await lead.page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(lead.page.getByText("Nothing pending.")).toBeVisible();

  // The lead runs a cycle.
  await lead.page.getByRole("link", { name: "Downtimes" }).click();
  await expect(lead.page.getByRole("heading", { name: "New cycle" })).toBeVisible();
  await lead.page.getByLabel("Name").fill("November");
  await lead.page.getByRole("button", { name: "Create draft" }).click();
  await lead.page.getByRole("link", { name: "November" }).click();
  await lead.page.getByRole("button", { name: "Open for submissions" }).click();
  await expect(lead.page.getByText("0 of 1 submitted")).toBeVisible();

  // The player answers and submits.
  await p.getByRole("link", { name: "Downtime", exact: true }).click();
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
  await p.getByRole("link", { name: "Results" }).click();
  await expect(p.getByText("you feed well and unseen")).toBeVisible();
  await p.screenshot(shots("results"));
});
