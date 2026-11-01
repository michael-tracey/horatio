import { expect, test } from "@playwright/test";
import { closeContextsAfterEach, shots, person, creatingVampire, tapMid, CAITIFF_THREE, ATTRIBUTES_AND_FOCUSES } from "./support";

/** The creation wizard: merits and flaws, and what each step lets a character take. */

closeContextsAfterEach();

test("Merits & flaws lists every flaw the character can take, without searching (#310)", async ({ browser }) => {
  const { page: p } = await person(browser, "every-flaw");
  const id = await creatingVampire(p, "Long List", "Caitiff", CAITIFF_THREE, ATTRIBUTES_AND_FOCUSES);
  await p.goto(`/characters/${id}/create/merits`);
  const flaws = p.getByRole("region", { name: "Flaws" });
  // What this character can take, more than 40, those late in the alphabet too.
  await expect(p.getByLabel("Show Flaws")).toHaveValue("can");
  expect(await flaws.getByRole("checkbox").count()).toBeGreaterThan(40);
  for (const name of ["Stolen Potential", "Thin Blooded"]) {
    const box = flaws.getByRole("checkbox", { name: new RegExp(`^${name}`) });
    await box.scrollIntoViewIfNeeded();
    await expect(box).toBeVisible();
  }
  await expect(p.getByText(/Search to see all/)).toHaveCount(0);
  // Everything: as many rows as the search says there are.
  await p.getByLabel("Show Flaws").selectOption("Everything");
  const count = Number((await p.getByLabel("Search Flaws").getAttribute("placeholder"))!.match(/\d+/)![0]);
  await expect(flaws.getByRole("checkbox")).toHaveCount(count);
});

test("Stolen Potential takes away the focus in the attribute it names, and the character finishes without one (#310)", async ({ browser }) => {
  const { page: p } = await person(browser, "stolen-potential");
  // Wits was chosen on Focuses before the flaw is taken.
  const id = await creatingVampire(p, "Hollow Promise", "Brujah", [], {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  await p.goto(`/characters/${id}/create/merits`);
  const flaw = p.getByRole("checkbox", { name: /^Stolen Potential/ });
  await flaw.scrollIntoViewIfNeeded();
  await flaw.check();
  // It asks which attribute.
  const which = p.getByLabel("Stolen Potential: which?");
  await expect(which.getByRole("option")).toHaveText(["Which?", "Physical", "Social", "Mental"]);
  await which.selectOption("Mental");
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Review", exact: true })).toBeVisible({ timeout: 15_000 });

  // Review says the Mental focus already chosen must go, and where.
  const settle = p.getByRole("region", { name: "Still to settle" });
  await expect(settle).toContainText("Stolen Potential: no starting mental focus. Take Wits back.");
  await settle.getByRole("link", { name: "Go to Focuses" }).click();
  await expect(p.getByRole("heading", { name: "Focuses", exact: true })).toBeVisible();
  await expect(p.getByRole("group", { name: "Changed by other steps" })).toContainText("Stolen Potential: no starting mental focus. Take Wits back.");
  await expect(p.getByRole("button", { name: "Wits 1" })).toHaveAttribute("aria-pressed", "true");
  await tapMid(p, "Clear Wits");
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Skills", exact: true })).toBeVisible({ timeout: 15_000 });

  // Focuses offers no Mental focus now, and says why; the others are as they were.
  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Focuses/ }).click();
  await expect(p.getByText("Stolen Potential: no Mental focus (p. 265).")).toBeVisible();
  await expect(p.getByRole("button", { name: "Wits 1" })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Charisma 1" })).toHaveAttribute("aria-pressed", "true");
  // The flaw is offered here too, taken.
  await expect(p.getByRole("region", { name: "From merits and flaws" }).getByRole("switch", { name: /^Stolen Potential/ })).toBeChecked();

  await p.getByRole("navigation", { name: "Creation steps" }).getByRole("link", { name: /Review/ }).click();
  await expect(p.getByRole("region", { name: "Still to settle" })).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();

  // The sheet holds the flaw, with its attribute, and no Mental focus.
  await expect(p.locator("section").filter({ has: p.getByRole("heading", { name: "Merits and Flaws", exact: true }) })).toContainText("Stolen Potential: Mental");
  await expect(p.getByText("Mental Focus", { exact: true })).toHaveCount(0);
  await expect(p.getByText("Social Focus", { exact: true }).first()).toBeVisible();
});

test("a bloodline's clan takes its merit from the merit points on Merits & flaws, another clan gives it back, and one that does not fit is refused (#313)", async ({ browser }) => {
  const { page: p } = await person(browser, "bloodline-merit");
  const id = await creatingVampire(p, "Urban Howl", "Gangrel: Coyote", [], { merits: [["Code of Honor", 2]] });
  await p.goto(`/characters/${id}/create/merits`);
  // The clan's merit, ticked and fixed, with why; its 2 points are spent with Code of Honor's.
  const fromClan = p.getByRole("region", { name: "From the clan" });
  await expect(fromClan.getByRole("checkbox", { name: "Bloodline: Coyote, given by the clan" })).toBeChecked();
  await expect(fromClan.getByRole("checkbox", { name: "Bloodline: Coyote, given by the clan" })).toBeDisabled();
  await expect(fromClan).toContainText("Gangrel: Coyote is a bloodline. (p. 238)");
  const merits = p.getByRole("region", { name: "Merits", exact: true });
  await expect(merits.getByText("4 of 7 points")).toBeVisible();
  // No bloodline merit is offered as a pick, even with everything shown.
  await p.getByLabel("Show Merits").selectOption("Everything");
  await expect(merits.getByRole("checkbox", { name: /^Bloodline: Noiad/ })).toHaveCount(0);

  // Concept says what the clan takes; a plain Gangrel gives it back.
  await p.goto(`/characters/${id}/create/concept`);
  await expect(p.getByText("The clan takes Bloodline: Coyote (2 points) from your merit points.")).toBeVisible();
  await p.getByLabel("Clan").selectOption("Gangrel");
  await expect(p.getByText("The clan takes Bloodline: Coyote (2 points) from your merit points.")).toHaveCount(0);
  await p.goto(`/characters/${id}/create/merits`);
  await expect(p.getByRole("region", { name: "From the clan" })).toHaveCount(0);
  await expect(p.getByRole("region", { name: "Merits", exact: true }).getByText("2 of 7 points")).toBeVisible();

  // With all 7 points spent, the Koldun's 4-point bloodline does not fit.
  const filled = await p.request.put(`/api/characters/${id}/creation/categories/merits`, {
    headers: { "X-Horatio": "1" },
    data: { picks: [{ name: "Code of Honor" }, { name: "Iron Will" }, { name: "Lucky" }] },
  });
  expect(filled.status(), await filled.text()).toBe(200);
  await p.goto(`/characters/${id}/create/concept`);
  await p.getByLabel("Clan").selectOption("Tzimisce: Koldun");
  await expect(p.getByText(/Tzimisce: Koldun needs Bloodline: Koldun \(4 points\), which does not fit: 7 of the 7 merit points are spent/)).toBeVisible();
  await expect(p.getByLabel("Clan")).toHaveValue("Gangrel");
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

test("a supplement's merit names its book, and a clan flaw says what it does (#315)", async ({ browser }) => {
  const { page: p } = await person(browser, "wf-book-pages");
  const id = await creatingVampire(p, "Old Tunnels", "Nosferatu: Creeps", [], ATTRIBUTES_AND_FOCUSES);
  await p.goto(`/characters/${id}/create/focuses`);
  const senses = p.getByRole("region", { name: "From merits" }).locator("label").filter({ hasText: "Extrasensory Perceptions" });
  await expect(senses).toContainText("(1-point merit, Vol. 2, p. 49)");

  await p.goto(`/characters/${id}/create/merits`);
  const flaws = p.getByRole("region", { name: "Flaws" });
  const anosmia = flaws.getByRole("checkbox", { name: /^Nosferatu: Anosmia/ });
  await anosmia.scrollIntoViewIfNeeded();
  await expect(anosmia).toHaveAccessibleName(/No sense of smell or taste/);
  await expect(flaws.getByText("Clan flaw for a second caste")).toHaveCount(0);
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
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
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
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
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
  await expect(settle).toContainText("Chosen of Cappadocius: choose the lore specialisations, languages and academics specialisations it gives.");
  await settle.getByRole("link", { name: "Go to Skills" }).click();

  const chosen = p.getByRole("group", { name: "Free traits from Chosen of Cappadocius" });
  for (const heading of ["Lore Specialisations", "Languages", "Academics Specialisations"]) {
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
  // Only the merit's own point comes from the budget, beside the clan's Bloodline: Creeps (2, #313).
  await expect(p.getByText("Bloodline: Creeps, Extrasensory Perceptions (3 of 7 points)")).toBeVisible();
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
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

test("a new player picks the clan first and sees its disciplines and weakness, and a phone shows the step reached (#372)", async ({ browser }) => {
  const { page: p } = await person(browser, "clan-first");
  await p.getByLabel("Name").fill("First Fangs");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  const phone = test.info().project.name === "phone";
  const steps = p.getByRole("navigation", { name: "Creation steps" });
  const bar = steps.getByRole("progressbar", { name: "Creation progress" });
  // On a phone the step reached is said in words over a bar; a wide screen has the whole list.
  const reached = async (text: string) => {
    await expect(steps.getByText(text, { exact: true })).toBeVisible();
    await expect(bar).toHaveAttribute("aria-valuetext", text.replace(" · ", ": "));
  };
  if (phone) await reached("Step 1 of 8 · Concept");
  else await expect(bar).toBeHidden();

  // The clan comes before the troupe question, and its card says what it brings.
  const top = async (label: string) => (await p.getByLabel(label).boundingBox())!.y;
  expect(await top("Clan")).toBeLessThan(await top("Which troupe will you play in?"));
  await p.getByLabel("Clan").selectOption("Brujah");
  const card = p.getByRole("region", { name: "About Brujah" });
  await expect(card).toContainText("In-clan now: Celerity, Potence and Presence.");
  await expect(card).toContainText("Weakness: Quick to rage: resisting frenzy is 2 harder. (p. 45)");
  // A bloodline with no weakness of its own has its clan's.
  await p.getByLabel("Clan").selectOption("Gangrel: Coyote");
  const coyote = p.getByRole("region", { name: "About Gangrel: Coyote" });
  await expect(coyote).toContainText("Weakness: One animal feature for good");
  await expect(coyote).toContainText("The clan takes Bloodline: Coyote (2 points) from your merit points.");
  await p.getByLabel("Clan").selectOption("Brujah");
  await expect(card).toContainText("In-clan now: Celerity, Potence and Presence.");
  await expect(card).not.toContainText("Bloodline: Coyote");

  // The in-clan merits are folded away as optional until opened.
  const fromMerits = p.getByRole("region", { name: "From merits" });
  await expect(fromMerits).toBeHidden();
  await p.getByText("Optional: in-clan disciplines from merits").click();
  await expect(fromMerits.getByRole("switch", { name: /^Additional Common Discipline/ })).toBeVisible();
  await p.screenshot(shots("creation-clan-card"));

  // Further on, the phone says which step of how many, and how many wait on Generation.
  await p.getByRole("button", { name: "Save and continue" }).click();
  await expect(p.getByRole("heading", { name: "Attributes", exact: true })).toBeVisible();
  if (phone) {
    await reached("Step 2 of 8 · Attributes");
    await expect(steps.getByText("3 locked", { exact: true })).toBeVisible();
  }
  await steps.getByRole("link", { name: /Backgrounds/ }).click();
  await expect(p.getByRole("heading", { name: "Backgrounds", exact: true })).toBeVisible();
  await expect(p.getByText(/^Generation is a background too, and a vampire needs at least 1 dot of it to go on\..*\(pp\. 100-101\)\.$/)).toBeVisible();
  if (phone) await reached("Step 5 of 8 · Backgrounds");
  await expect(steps.getByText(/^Finish Backgrounds to open the steps after it/)).toBeVisible();
  await p.screenshot(shots("creation-progress"));

  // Review lists what is still to place, each with the way to its step.
  await p.goto(p.url().replace(/backgrounds$/, "review"));
  const left = p.getByRole("region", { name: "Picks left" });
  await expect(left).toContainText("Attributes at 7: 1 left. Go to Attributes");
  await left.getByRole("link", { name: "Go to Attributes" }).first().click();
  await expect(p.getByRole("heading", { name: "Attributes", exact: true })).toBeVisible();
});

test("each step keeps its picks as they are made, through the step list and a reload, and Finish creation asks first (#357)", async ({ browser }) => {
  const { page: p } = await person(browser, "keeps-picks");
  const id = await creatingVampire(p, "Kept Taps", "Brujah", [], {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  await p.goto(`/characters/${id}/create/skills`);
  await expect(p.getByRole("heading", { name: "Skills", exact: true })).toBeVisible();

  // While she is being created, the page leads back here, not to Play, and the tabs for play wait.
  await expect(p.getByRole("link", { name: "Continue creating" })).toBeVisible();
  await expect(p.getByRole("link", { name: "Play", exact: true })).toHaveCount(0);
  for (const tab of ["Experience", "Downtime", "Results", "Influence"]) await expect(p.locator("main").getByRole("link", { name: tab, exact: true })).toHaveCount(0);

  // Taps not yet saved go with the player to another step, and are there on coming back.
  const steps = p.getByRole("navigation", { name: "Creation steps" });
  await tapMid(p, "Brawl 4");
  await tapMid(p, "Dodge 3");
  await steps.getByRole("link", { name: /Backgrounds/ }).click();
  await expect(p.getByRole("heading", { name: "Backgrounds", exact: true })).toBeVisible();
  await steps.getByRole("link", { name: /Skills/ }).click();
  await expect(p.getByRole("button", { name: "Brawl 4", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(p.getByRole("button", { name: "Dodge 3", exact: true })).toHaveAttribute("aria-pressed", "true");

  // The step saves itself a moment after the last tap, and a reload keeps it all.
  for (const dot of ["Athletics 3", "Awareness 2", "Empathy 2", "Firearms 2", "Investigation 1", "Leadership 1", "Medicine 1", "Melee 1"]) await tapMid(p, dot);
  await expect(p.getByText(/^Saved \d/)).toBeVisible({ timeout: 15_000 });
  await p.screenshot(shots("creation-saved"));
  await p.reload();
  for (const dot of ["Brawl 4", "Athletics 3", "Melee 1"]) await expect(p.getByRole("button", { name: dot, exact: true })).toHaveAttribute("aria-pressed", "true");

  // Review sums her up before finishing (#372).
  await steps.getByRole("link", { name: /Review/ }).click();
  const summary = p.getByRole("region", { name: "Summary" });
  await expect(summary).toContainText("Kept Taps so far");
  await expect(summary).toContainText("Brujah. In-clan: Celerity, Potence and Presence.");
  await expect(summary).toContainText("Physical 7 (Strength), Social 5 (Charisma), Mental 3 (Wits)");
  await expect(summary).toContainText("Brawl 4, Athletics 3, Dodge 3, Awareness 2, Empathy 2, and 5 more");
  await expect(summary).toContainText("Celerity 2, Potence 1, Presence 1");
  await expect(summary).toContainText("Fame 3, Resources 2, Generation background ●");
  await expect(summary).toContainText("None (0 of 7 points)");
  await expect(p.getByRole("region", { name: "Picks left" })).toHaveCount(0);
  await p.screenshot(shots("creation-review"));

  // Finishing asks first and says what changes; Not yet leaves her in creation.
  await p.getByRole("button", { name: "Finish creation" }).click();
  await expect(p.getByText("Finish creating Kept Taps? After this, the starting picks are fixed and new dots cost XP.")).toBeVisible();
  await p.screenshot(shots("creation-finish-asks"));
  await p.getByRole("button", { name: "Not yet" }).click();
  await expect(p.getByText(/^Finish creating Kept Taps\?/)).toHaveCount(0);
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  await expect(p.getByRole("link", { name: "Play", exact: true })).toBeVisible();
  await expect(p.getByRole("link", { name: "Continue creating" })).toHaveCount(0);
});

test("on a phone the rating dots are big enough to tap, and a locked step says why in words (#361)", async ({ browser }) => {
  const { page: p } = await person(browser, "big-dots");
  // No Generation yet: the steps after Backgrounds are locked.
  const id = await creatingVampire(p, "Thumb Taps", "Brujah", []);
  await p.goto(`/characters/${id}/create/skills`);
  await expect(p.getByRole("heading", { name: "Skills", exact: true })).toBeVisible();

  // At least 40px on a touch screen; the desktop keeps its compact rows.
  const dot = (await p.getByRole("button", { name: "Brawl 1", exact: true }).boundingBox())!;
  if (test.info().project.name === "phone") {
    expect(dot.width).toBeGreaterThanOrEqual(40);
    expect(dot.height).toBeGreaterThanOrEqual(40);
  } else expect(dot.height).toBeLessThan(40);
  // Clear stands apart from the last dot.
  await tapMid(p, "Brawl 4");
  const last = (await p.getByRole("button", { name: "Brawl 4", exact: true }).boundingBox())!;
  const clear = (await p.getByRole("button", { name: "Clear Brawl" }).boundingBox())!;
  expect(clear.x - (last.x + last.width)).toBeGreaterThanOrEqual(test.info().project.name === "phone" ? 12 : 4);

  // The reason a step is locked is on the screen, not in a hover title, and read with the step.
  const steps = p.getByRole("navigation", { name: "Creation steps" });
  const why = /^Finish Backgrounds to open the steps after it: A vampire needs at least 1 dot of Generation/;
  await expect(steps.getByText(why)).toBeVisible();
  await expect(steps.getByText(/Disciplines/)).toHaveAccessibleDescription(why);
  await p.screenshot(shots("creation-locked-why"));
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
  await expect(p.getByRole("region", { name: "Summary" })).toContainText("Brawl 4, Performance: Singing 3, Science: Chemistry 3");
  await expect(p.getByText("Crafts needs a field:")).toBeVisible();
  await expect(p.getByRole("link", { name: "Back to Skills" })).toBeVisible();
  await expect(p.getByRole("button", { name: "Finish creation" })).toBeDisabled();
  await p.getByLabel("Crafts field").fill("Woodwork");
  await p.getByRole("button", { name: "Set" }).click();
  await expect(p.getByText("Crafts needs a field:")).toHaveCount(0);
  await expect(p.getByRole("button", { name: "Finish creation" })).toBeEnabled();
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Character creation" })).toHaveCount(0);
  const part = (title: string) => p.locator("section").filter({ has: p.getByRole("heading", { name: title, exact: true }) });
  for (const skill of ["Performance: Singing", "Performance: Dance", "Science: Chemistry", "Crafts: Woodwork"])
    await expect(part("Skills").getByText(skill, { exact: true })).toBeVisible();
});
