/**
 * In-clan disciplines, chosen on Concept: a Caitiff's three (core p. 246), and the
 * one a merit adds for any clan (pp. 242, 248). The merit's choice is also offered
 * under it on Merits, on Disciplines while it is open, and from Review (#216). Which disciplines each allows is the
 * server's to say (`GET /unavailable`); this only counts the choices and words them.
 */

import type { SheetOut, SheetTraitOut } from "../../../api/types";
import { EXTRA_IN_CLAN, inOrder, type NoticeSource } from "./notices";

export { EXTRA_IN_CLAN };

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

/** Whether taking a merit makes an in-clan choice: one of IN_CLAN_MERITS, or a troupe's own that adds one. */
export function makesInClanChoice(trait: { name: string; house?: { in_clan?: string[] | null } | null }): boolean {
  return IN_CLAN_MERITS.includes(trait.name) || (trait.house?.in_clan?.length ?? 0) > 0;
}

const holds = (sheet: SheetOut, name: string) => sheet.traits.some((t) => t.category === "merits" && t.name === name && (t.rating ?? 0) > 0);

/** A troupe's own merit held that adds one in-clan discipline, as Additional Common Discipline does, and from where. */
function houseAdding(sheet: SheetOut): [string, string] | undefined {
  const merit = sheet.traits.find((t) => t.category === "merits" && (t.rating ?? 0) > 0 && (t.house?.in_clan?.length ?? 0) > 0);
  if (!merit) return undefined;
  const list = merit.house!.in_clan!;
  return [merit.name, `from ${list.length > 1 ? `${list.slice(0, -1).join(", ")} or ${list.at(-1)}` : list[0]}`];
}

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
  const house = houseAdding(sheet);
  const adding = Object.keys(ADDS_ONE).find((m) => holds(sheet, m)) ?? house?.[0];
  const from = adding && (ADDS_ONE[adding] ?? house?.[1]);
  const lines: string[] = [];
  if (caitiff) {
    lines.push(
      holds(sheet, "Vestiges of Greatness")
        ? "Two from the common ones and one from the uncommon ones (Vestiges of Greatness)."
        : "Caitiff choose their three in-clan disciplines from the common ones.",
    );
    if (holds(sheet, "Inceptor")) lines.push("One of them can be Kineticism, or one path of Thaumaturgy or Necromancy (Inceptor).");
  }
  if (adding) lines.push(`${caitiff ? "And a fourth" : "One extra in-clan discipline"} ${from} (${adding}).`);
  return {
    chooses: (caitiff ? 3 : 0) + (adding ? 1 : 0),
    chosen: held.filter((t) => !isGiven(t)),
    given: held.filter(isGiven),
    lines,
    adding,
    caitiff,
  };
}

/**
 * The disciplines the picker offers: those held, and every one the server does not
 * bar whatever is chosen (`barred`, worked out as if none were). One the rules refuse
 * only as things stand (a fourth for a Caitiff, a second from Vestiges' list) is
 * offered, and tapping it asks what to swap out (`whenTapped`).
 */
export function inClanOptions(names: string[], choice: InClanChoice, barred: Record<string, string>): string[] {
  const held = new Set([...choice.chosen, ...choice.given].map((t) => t.name));
  return names.filter((name) => held.has(name) || !(name in barred));
}

/** What tapping an unticked discipline does: chosen at once, or, where the rules refuse it now, the swaps that make room. */
export function whenTapped(name: string, refused: Record<string, string>): "choose" | "swap" {
  return name in refused ? "swap" : "choose";
}

/**
 * Whether an in-clan choice waits on the player: one still to choose, or a merit's
 * check that wants a different one (Vestiges of Greatness: one from the uncommon list).
 */
export function inClanOpen(sheet: SheetOut): boolean {
  const { chooses, chosen } = inClanChoice(sheet);
  if (chooses > chosen.length) return true;
  return sheet.problems.some(
    (p) => p.category === "merits" && (p.strength === "complete" || p.strength === "refuse") && sheet.traits.some((t) => t.category === "merits" && t.name === p.name && makesInClanChoice(t)),
  );
}

/**
 * A short key for the sheet as it stands: the traits held and their ratings. What the
 * server says the character can choose is asked again for each, so an answer from
 * before a change (taking Vestiges of Greatness) is never shown as if it were now's.
 */
export function sheetKey(sheet: SheetOut): string {
  const held = sheet.traits.map((t) => `${t.category}/${t.name}/${t.detail}/${t.rating ?? ""}`).sort().join("|");
  let hash = 5381;
  for (let i = 0; i < held.length; i++) hash = ((hash * 33) ^ held.charCodeAt(i)) >>> 0;
  return `${sheet.traits.length}-${hash.toString(36)}`;
}

/** In-clan disciplines still to choose: on Concept, and on Merits when a merit there added the choice. */
export const inClanChoices: NoticeSource = ({ sheet, steps, ghoul }) => {
  // A ghoul chooses none: its in-clan disciplines are its domitor's.
  if (ghoul) return [];
  const { chooses, chosen, adding, caitiff } = inClanChoice(sheet);
  const left = chooses - chosen.length;
  if (left <= 0) return [];
  const merit = adding && (!caitiff || left === 1);
  // The merit's own check says the same, with its page: that one is shown (brokenChecks).
  if (merit && sheet.problems.some((p) => p.category === "merits" && p.name === adding)) return [];
  const message = merit
    ? `${adding}: choose the in-clan discipline it adds.`
    : `Choose ${left}${left < chooses ? " more" : ""} in-clan ${left === 1 ? "discipline" : "disciplines"}.`;
  return [{ key: "in-clan/choose", message, on: inOrder(steps, ["concept", adding ? "merits" : undefined]), fix: "concept", inClan: true }];
};
