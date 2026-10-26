/**
 * A ghoul's domitor (MET: VTM pp. 296–297): the vampire it is bound to, whose clan
 * and in-clan disciplines it takes. Which domitor it may have, and where its dots
 * may go, is the server's to say; this works out what the form shows and sends.
 */

import type { CatalogueOut, DomitorChoiceOut, DomitorIn, SheetOut } from "../../api/types";

/** The clan with no in-clan disciplines of its own: its player names the three it chose (p. 246). */
export const CAITIFF = "Caitiff";
export const CAITIFF_CHOOSES = 3;

/** Where a Caitiff domitor's three come from in a ghoul's catalogue. */
export const DOMITOR_IN_CLAN = "domitor_in_clan_disciplines";

/** A domitor as the form holds it: a vampire in Horatio, or one named, with its clan. */
export type DomitorDraft =
  | { kind: "linked"; choice: DomitorChoiceOut | null }
  | { kind: "named"; name: string; clan: string; three: string[] };

/** The clans a named domitor can be of, and the disciplines a Caitiff one can have chosen. */
export function clansOf(catalogue: CatalogueOut): string[] {
  return catalogue.traits.filter((t) => t.category === "clan").map((t) => t.name);
}

export function caitiffChoices(catalogue: CatalogueOut): string[] {
  return catalogue.traits.filter((t) => t.category === DOMITOR_IN_CLAN).map((t) => t.name);
}

/** The in-clan disciplines the ghoul would take from the domitor: its clan's, or a Caitiff's three. */
export function inClanOf(draft: DomitorDraft, catalogue: CatalogueOut): string[] {
  if (draft.kind === "linked") return draft.choice?.in_clan ?? [];
  if (draft.clan === CAITIFF) return draft.three.filter(Boolean);
  return catalogue.traits.find((t) => t.category === "clan" && t.name === draft.clan)?.in_clan ?? [];
}

/** What is still missing before the domitor can be saved, or null when nothing is. */
export function draftMissing(draft: DomitorDraft): string | null {
  if (draft.kind === "linked") return draft.choice ? null : "Choose the vampire.";
  if (!draft.name.trim()) return "Give the domitor's name.";
  if (!draft.clan) return "Choose the domitor's clan.";
  if (draft.clan === CAITIFF) {
    const named = draft.three.filter(Boolean);
    if (named.length < CAITIFF_CHOOSES || new Set(named).size < CAITIFF_CHOOSES) return `Name the ${CAITIFF_CHOOSES} in-clan disciplines the Caitiff chose, each once.`;
  }
  return null;
}

/** The discipline dots the ghoul has now, which a new domitor's ghoul keeps or moves. */
export function disciplineDots(sheet: SheetOut): { name: string; detail: string; rating: number }[] {
  return sheet.traits.filter((t) => t.category === "disciplines" && (t.rating ?? 0) > 0).map((t) => ({ name: t.name, detail: t.detail, rating: t.rating! }));
}

/** The body that binds the ghoul to the domitor drafted: keeping its discipline dots, or moving them as `moved` says. */
export function domitorBody(draft: DomitorDraft, disciplines: "keep" | "move", moved: Record<string, number>): DomitorIn {
  const where =
    draft.kind === "linked"
      ? { character_id: draft.choice!.character_id, name: "", clan: null, in_clan: [] }
      : { character_id: null, name: draft.name.trim(), clan: draft.clan, in_clan: draft.clan === CAITIFF ? draft.three : [] };
  return {
    ...where,
    disciplines,
    moved:
      disciplines === "move"
        ? Object.entries(moved)
            .filter(([, rating]) => rating > 0)
            .map(([name, rating]) => ({ name, rating, detail: "" }))
        : [],
  };
}
