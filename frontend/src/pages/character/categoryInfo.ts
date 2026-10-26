import type { CatalogueOut } from "../../api/types";

/**
 * What the sheet's headings and the page title's choices are, in a line or two
 * of our own words. The rules data describes traits but not categories, so this
 * is the only home for this copy; a heading with no entry here gets no ⓘ.
 */

/** The parts of the sheet (the card titles), by name. */
const PARTS: Record<string, string> = {
  Attributes: "Physical, Social and Mental: the three pools a character is tested with. Each has a focus that says what it is best at.",
  Expended: "What is spent during play, such as Willpower. Worked out from the rest of the sheet, so nothing here is bought.",
  Skills: "What the character has learned to do, from Brawl to Investigation. Each is rated in dots.",
  Disciplines: "The vampire's supernatural powers. The clan's own disciplines, the in-clan ones, cost less to learn than the rest.",
  Morality: "How firmly the character holds to Humanity, or to the Path they follow in its place. A character follows one at a time.",
  Backgrounds: "What the character has in the world around them, such as Allies, Contacts and Resources, and their Generation. Rated in dots, usually up to 5.",
  "Merits and Flaws": "Merits are advantages and flaws are drawbacks. Each has a fixed value in points, not dots.",
};

/** The choices in the page title, by category key. */
const CHOICES: Record<string, string> = {
  clan: "The bloodline the character belongs to. It decides which disciplines are in-clan, and so cheaper to learn.",
  archetype: "A word or two for the character's personality, as a guide to playing them. Once an hour, a test that fits it gets a free Willpower retest, in place of the usual one.",
  sect: "The political society the character belongs to, such as the Camarilla or the Sabbat.",
  faction: "For a Sabbat vampire, the faction within the sect that they belong to.",
};

/** What a part of the sheet is, and the price the catalogue gives for it; null if there is nothing to say. */
export function partInfo(part: string, catalogue: CatalogueOut | undefined): { about: string; facts: string[] } | null {
  const about = PARTS[part];
  if (!about) return null;
  const facts: string[] = [];
  const swap = catalogue?.categories.find((c) => c.group === part && c.key.startsWith("focus_") && c.change_cost != null);
  if (swap) facts.push(`After creation, swapping a focus for another costs ${swap.change_cost} XP.`);
  return { about, facts };
}

/** What a category under a part's card is (Merits, Flaws), with its limit from the catalogue; null if there is nothing to say. */
export function categoryInfo(key: string, catalogue: CatalogueOut | undefined): { about: string; facts: string[] } | null {
  const limit = catalogue?.categories.find((c) => c.key === key)?.points_limit;
  if (key === "merits")
    return { about: "Advantages, each with a fixed value in points.", facts: limit != null ? [`A character holds at most ${limit} points of merits.`] : [] };
  if (key === "flaws")
    return { about: "Drawbacks that pay the character XP for taking them.", facts: limit != null ? [`Flaws pay out at most ${limit} XP in all.`] : [] };
  return null;
}

/** What a choice in the page title is (clan, archetype…), or null for one with no copy. */
export function choiceInfo(category: string): string | null {
  return CHOICES[category] ?? null;
}
