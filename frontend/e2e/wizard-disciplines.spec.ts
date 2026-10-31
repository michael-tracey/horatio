import { expect, test } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, creatingVampire, tapMid, CAITIFF_THREE, ATTRIBUTES_AND_FOCUSES } from "./support";

/** The creation wizard's in-clan disciplines: Caitiff, Vestiges of Greatness and the merits that change them. */

closeContextsAfterEach();

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
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
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
  // Each swap is tried on the server as a whole cart, three at once: on CI's busy server the slowest takes up to 5 s (#334).
  await expect(room.getByRole("button", { name: /^Swap / })).toHaveCount(3, { timeout: 15_000 });
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
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
});

// #216, as the player built it: every step in order, Vestiges of Greatness taken on
// Merits, and its choice made there, with no reload and no going back to Concept.
for (const forTroupe of [false, true]) {
  test(`a Caitiff builds step by step, takes Vestiges of Greatness on Merits, chooses Protean under it and finishes${forTroupe ? ", built for a troupe" : ""}`, async ({ browser }) => {
    test.slow();
    const { page: p } = await person(browser, forTroupe ? "vg-player" : "vg-forward");
    const troupeName = `Court of Remnants ${run}`;
    if (forTroupe) {
      const custodian = await person(browser, "vg-custodian");
      makeCustodian(custodian.email);
      const lead = await person(browser, "vg-lead");
      const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
      expect(made.status(), await made.text()).toBe(201);
      await p.reload();
    }
    await p.getByLabel("Name").fill("Hand-Me-Down");
    if (forTroupe) await p.getByLabel("Build for").selectOption({ label: troupeName });
    await p.getByRole("button", { name: "Create" }).click();
    await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
    await p.getByLabel("Clan").selectOption("Caitiff");
    for (const name of ["Celerity", "Fortitude", "Obfuscate"]) {
      await p.getByRole("checkbox", { name }).click();
      await expect(p.getByRole("checkbox", { name })).toBeChecked();
    }
    const next = async (heading: string) => {
      await p.getByRole("button", { name: "Save and continue" }).click();
      await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
    };
    const tap = async (...dots: string[]) => {
      for (const dot of dots) await p.getByRole("button", { name: dot, exact: true }).click();
    };
    await next("Attributes");
    await tap("Mental 7", "Physical 5", "Social 3");
    await next("Focuses");
    await tap("Perception 1", "Dexterity 1", "Charisma 1");
    await next("Skills");
    await tap("Drive 4", "Dodge 3", "Firearms 3", "Brawl 2", "Melee 2", "Survival 2", "Animal Ken 1", "Athletics 1", "Security 1", "Stealth 1");
    await next("Backgrounds");
    await tap("Contacts 3", "Fame 2", "Generation 1");
    await next("Disciplines");
    await tap("Celerity 2", "Fortitude 1", "Obfuscate 1");
    await next("Merits & flaws");

    // Taking the merit offers its choice under it at once: the uncommon ones, with swaps.
    await p.getByLabel("Search Merits").fill("Vestiges");
    await p.getByRole("checkbox", { name: /^Vestiges of Greatness/ }).check();
    await expect(p.getByText("Two from the common ones and one from the uncommon ones (Vestiges of Greatness).")).toBeVisible({ timeout: 15_000 });
    await expect(p.getByRole("group", { name: "Changed by other steps" })).toContainText("Vestiges of Greatness: choose one of your in-clan disciplines from Dementation");
    await expect(p.getByRole("group", { name: "Changed by other steps" })).toContainText("Choose it under the merit, below.");
    await expect(p.getByRole("group", { name: "Changed by other steps" }).getByRole("link", { name: "Go to Concept" })).toHaveCount(0);
    await p.getByRole("checkbox", { name: "Protean", exact: true }).click();
    const room = p.getByRole("group", { name: "Make room for Protean" });
    // Each swap is tried on the server as a whole cart, three at once: on CI's busy server the slowest takes up to 5 s (#334).
    await expect(room.getByRole("button", { name: /^Swap / })).toHaveCount(3, { timeout: 15_000 });
    await room.getByRole("button", { name: "Swap Obfuscate for Protean" }).click();
    await expect(p.getByRole("checkbox", { name: "Protean", exact: true })).toBeChecked();
    await expect(p.getByText("Vestiges of Greatness: choose one")).toHaveCount(0);

    // The starting dot on Obfuscate moves to Protean at a tap, from here too.
    await p.getByRole("group", { name: "Starting dots to move" }).getByRole("button", { name: "Move the dot from Obfuscate to Protean" }).click();
    // Moving saves Disciplines, and asks again for everything on Merits: as slow as a step's save.
    await expect(p.getByRole("group", { name: "Starting dots to move" })).toHaveCount(0, { timeout: 15_000 });
    await expect(p.getByText("Your starting dot in Obfuscate needs moving")).toHaveCount(0);
    await p.screenshot(shots(`vestiges-on-merits${forTroupe ? "-troupe" : ""}`));
    await next("Review");
    await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
    await expect(p.getByRole("listitem").filter({ hasText: "Disciplines at 1" })).toContainText("Protean");
    await p.getByRole("button", { name: "Finish creation" }).click();
    await p.getByRole("button", { name: "Yes, finish creation" }).click();
    await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  });
}

test("a Caitiff with Vestiges of Greatness is shown its choice on Disciplines, makes it from Review, moves the dots there and finishes", async ({ browser }) => {
  const { page: p } = await person(browser, "vg-review");
  const id = await creatingVampire(p, "Jumble", "Caitiff", ["Celerity", "Fortitude", "Obfuscate"], {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Fortitude", 1], ["Obfuscate", 1]],
    merits: [["Vestiges of Greatness", 3]],
  });

  // Disciplines shows the choice while it is open, at the top.
  await p.goto(`/characters/${id}/create/disciplines`);
  await expect(p.getByText("Two from the common ones and one from the uncommon ones (Vestiges of Greatness).")).toBeVisible();
  await expect(p.getByRole("checkbox", { name: "Protean" })).toBeVisible();

  // Review's notice opens it in place.
  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Review/ }).click();
  const settle = p.getByRole("region", { name: "Still to settle" });
  await expect(settle).toContainText("Vestiges of Greatness: choose one of your in-clan disciplines from Dementation");
  await settle.getByRole("button", { name: "Choose here" }).click();
  await p.getByRole("region", { name: "In-clan choice" }).getByRole("checkbox", { name: "Dementation" }).click();
  await p.getByRole("group", { name: "Make room for Dementation" }).getByRole("button", { name: "Swap Celerity for Dementation" }).click();
  await expect(p.getByRole("checkbox", { name: "Dementation" })).toBeChecked();

  // The two dots on Celerity move to Dementation from Review too, and it finishes.
  await p.getByRole("button", { name: "Move the dots from Celerity to Dementation" }).click();
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0, { timeout: 15_000 });
  await expect(p.getByRole("listitem").filter({ hasText: "Disciplines at 2" })).toContainText("Dementation");
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
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
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
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
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
});

test("an Angelis Ater chooses its third in-clan discipline on Disciplines, places its starting dots and finishes (#312)", async ({ browser }) => {
  const { page: p } = await person(browser, "angelis-ater");
  const id = await creatingVampire(p, "Black Angel", "Baali: Angelis Ater", [], {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
  });
  await p.goto(`/characters/${id}/create/disciplines`);
  await expect(p.getByRole("heading", { name: "Disciplines", exact: true })).toBeVisible();
  // Two in-clan disciplines for three picks: the step says what the third waits on, and offers it.
  await expect(p.getByText("Baali: Angelis Ater: choose one more in-clan discipline, Potence, Presence or Obfuscate (p. 72).")).toBeVisible();
  await expect(p.getByText("In-clan now: Daimoinon and Dominate.")).toBeVisible();
  const choice = p.getByRole("group", { name: /In-clan choice/ });
  await expect(choice.getByRole("radio")).toHaveCount(3);
  await choice.getByRole("radio", { name: "Presence" }).check();
  await expect(p.getByText("In-clan now: Daimoinon, Dominate and Presence.")).toBeVisible();
  await expect(p.getByText("Baali: Angelis Ater: choose one more")).toHaveCount(0);

  await p.getByRole("button", { name: "Daimoinon 2" }).click();
  await p.getByRole("button", { name: "Dominate 1" }).click();
  await p.getByRole("button", { name: "Presence 1" }).click();
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Merits & flaws", exact: true })).toBeVisible({ timeout: 15_000 });

  // Concept shows the choice made.
  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Concept/ }).click();
  await expect(p.getByRole("group", { name: /In-clan choice/ }).getByRole("radio", { name: "Presence" })).toBeChecked();

  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Review/ }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible();
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
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
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
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
