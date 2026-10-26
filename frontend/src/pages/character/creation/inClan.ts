/**
 * In-clan disciplines, chosen on Concept: a Caitiff's three (core p. 246), and the
 * one a merit adds for any clan (pp. 242, 248). Which disciplines each allows is the
 * server's to say (`GET /unavailable`); this only counts the choices and words them.
 */

import type { SheetOut, SheetTraitOut } from "../../../api/types";
import { inOrder, type NoticeSource } from "./notices";

export const EXTRA_IN_CLAN = "extra_in_clan_disciplines";

/** Merits that change in-clan disciplines, offered on Concept as well as on Merits. */
export const IN_CLAN_MERITS = [
  "Vestiges of Greatness",
  "Inceptor",
  "Additional Common Discipline",
  "Additional Uncommon Discipline",
  "Pliable Blood",
  "Bonds of Stolen Vitae",
];

/** Merits that add one in-clan discipline chosen here, and where it comes from. */
const ADDS_ONE: Record<string, string> = {
  "Additional Common Discipline": "from the common ones",
  "Additional Uncommon Discipline": "from the uncommon ones",
  "Pliable Blood": "from those it allows",
};

const holds = (sheet: SheetOut, name: string) => sheet.traits.some((t) => t.category === "merits" && t.name === name && (t.rating ?? 0) > 0);

/** What another trait gives here (Web of Knives' Potence) is held, not chosen. */
export function isGiven(trait: SheetTraitOut): boolean {
  return trait.granted_rating > 0 && trait.granted_rating >= (trait.rating ?? 0);
}

export type InClanChoice = {
  /** How many the player chooses; 0 if none. */
  chooses: number;
  /** The ones chosen, and the ones other traits give. */
  chosen: SheetTraitOut[];
  given: SheetTraitOut[];
  /** The rule as it stands for this character, a line per merit that changes it. */
  lines: string[];
  /** The merit that adds a choice, if any. */
  adding?: string;
  caitiff: boolean;
};

export function inClanChoice(sheet: SheetOut): InClanChoice {
  const caitiff = sheet.traits.some((t) => t.category === "clan" && t.name === "Caitiff");
  const held = sheet.traits.filter((t) => t.category === EXTRA_IN_CLAN && (t.rating ?? 0) > 0);
  const adding = Object.keys(ADDS_ONE).find((m) => holds(sheet, m));
  const lines: string[] = [];
  if (caitiff) {
    lines.push(
      holds(sheet, "Vestiges of Greatness")
        ? "Two from the common ones and one from the uncommon ones (Vestiges of Greatness)."
        : "Caitiff choose their three in-clan disciplines from the common ones.",
    );
    if (holds(sheet, "Inceptor")) lines.push("One of them can be Kineticism, or one path of Thaumaturgy or Necromancy (Inceptor).");
  }
  if (adding) lines.push(`${caitiff ? "And a fourth" : "One extra in-clan discipline"} ${ADDS_ONE[adding]} (${adding}).`);
  return {
    chooses: (caitiff ? 3 : 0) + (adding ? 1 : 0),
    chosen: held.filter((t) => !isGiven(t)),
    given: held.filter(isGiven),
    lines,
    adding,
    caitiff,
  };
}

/** In-clan disciplines still to choose: on Concept, and on Merits when a merit there added the choice. */
export const inClanChoices: NoticeSource = ({ sheet, steps }) => {
  const { chooses, chosen, adding, caitiff } = inClanChoice(sheet);
  const left = chooses - chosen.length;
  if (left <= 0) return [];
  const message =
    adding && (!caitiff || left === 1)
      ? `${adding}: choose the in-clan discipline it adds.`
      : `Choose ${left}${left < chooses ? " more" : ""} in-clan ${left === 1 ? "discipline" : "disciplines"}.`;
  return [{ key: "in-clan/choose", message, on: inOrder(steps, ["concept", adding ? "merits" : undefined]), fix: "concept" }];
};
