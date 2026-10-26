/**
 * Merits and flaws that change the Focuses, Skills and Backgrounds steps (#192, part 3):
 * which to offer on each, and the cross-step notices for what they give. What a merit
 * gives, and whether a pick is spent for nothing, is the server's to say (the creation
 * pools' `freed_by` and `given`, and the free traits a held merit offers); this words
 * it, and says which step it lands on.
 */

import type { CreationOut } from "../../../api/types";
import { inOrder, listed, stepFor, type NoticeSource, type StepNotice } from "./notices";

const merits = (names: string[]) => names.map((name) => ({ category: "merits", name }));
const flaws = (names: string[]) => names.map((name) => ({ category: "flaws", name }));

/** Merits that add a focus to choose (Versatile, Expanded Consciousness) or give one. */
export const FOCUS_MERITS = merits([
  "Versatile",
  "Expanded Consciousness",
  "Angelic Visage",
  "Extrasensory Perceptions",
  "Dust in the Wind",
  "Art Imitates Life",
  "Beauty of the Beholder",
]);

/** Merits that make dots in a skill free (both spellings of Blood of the Tzimisce are in the data), and Chosen of Cappadocius' specialisations. */
export const SKILL_MERITS = merits([
  "All the Best Toys",
  "Artist's Blessing",
  "Blood of the Tzimisce",
  "Blood of Tzimisce",
  "Seasoned Traveler",
  "Chosen of Cappadocius",
]);

/** Merits that make dots in a background free, or place the dots the player chooses (Ventrue Royalty); and the flaws that set the Generation. */
export const BACKGROUND_MERITS = [
  ...merits(["Consecrated Grove", "Diva", "Personal Cult", "Ventrue Royalty"]),
  ...flaws(["Lesser Generation 1", "Lesser Generation 2", "Thin Blooded"]),
];

const causes = (refs: { name?: string | null }[]): string[] => [...new Set(refs.map((r) => r.name).filter((n): n is string => !!n))];

/**
 * A creation pick spent on a trait a merit now gives free (Personal Cult makes Herd
 * free to 5): the pick is kept, marked where it was placed, and can go elsewhere.
 */
export const freedPicks: NoticeSource = ({ creation, steps }) =>
  creation.pools.flatMap((pool) =>
    pool.traits
      .filter((t) => t.freed_by && t.freed_by.length > 0)
      .map((t): StepNotice | null => {
        const placed = stepFor(steps, pool.category)?.key;
        if (!placed) return null;
        const by = causes(t.freed_by!);
        return {
          key: `freed/${pool.category}/${t.name}/${t.detail}`,
          message: `${listed(by)} makes ${t.name} free: your pick on ${t.name} can go elsewhere.`,
          on: inOrder(steps, [placed, ...t.freed_by!.map((b) => stepFor(steps, b.category)?.key)]),
          fix: placed,
          trait: { category: pool.category, name: t.name },
        };
      })
      .filter((n): n is StepNotice => n !== null),
  );

/**
 * A merit that gives free traits the player chooses (Ventrue Royalty's backgrounds,
 * Chosen of Cappadocius' specialisations) with some still to choose. It is shown on the
 * step the gift lands on, which is where it is chosen, and on Merits & flaws.
 */
export const unchosenFree: NoticeSource = ({ sheet, steps }) =>
  sheet.traits.flatMap((t): StepNotice[] => {
    const open = (t.free_choices ?? []).filter((o) => !o.complete && !o.locked);
    if (!open.length || (t.rating ?? 0) <= 0) return [];
    const lands = inOrder(steps, open.map((o) => stepFor(steps, o.category)?.key));
    const here = stepFor(steps, t.category)?.key;
    const on = inOrder(steps, [here, ...lands]);
    if (!on.length) return [];
    return [
      {
        key: `free/${t.category}/${t.name}/${t.detail}`,
        message: `${t.name}: choose the ${listed(open.map((o) => o.category_name.toLowerCase()))} it gives.`,
        on,
        fix: lands[0] ?? on[0]!,
      },
    ];
  });

/**
 * The traits merits give in a category, held without a pick: why a pick cannot go on
 * each, by name ("Diva gives you Fame 2 free."). Shown as held on the step.
 */
export function givenIn(creation: CreationOut, category: string): Record<string, { rating: number; text: string }> {
  const found: Record<string, { rating: number; text: string }> = {};
  for (const g of creation.given ?? []) {
    if (g.category !== category) continue;
    const by = causes(g.because);
    found[g.name] = { rating: g.rating, text: `${by.length ? `${listed(by)} gives` : "You are given"} you ${g.name}${g.rating > 1 ? ` ${g.rating}` : ""} free.` };
  }
  return found;
}
