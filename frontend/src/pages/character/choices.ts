import type { CatalogueOut, TraitOut } from "../../api/types";
import { usePlannedUnavailable, useUnavailable } from "../../hooks";
import { toChange, type CartLine } from "./cart";
import { byKind, takeable } from "./traitFilter";

/** What a character can take in one category of a part of the sheet. */
export type Choices = {
  key: string;
  name: string;
  /** The category's whole list. */
  traits: TraitOut[];
  /** Refused now, with the reason: shown greyed. */
  refused: Record<string, string>;
  /** Not held, and not refused now: what the chip counts. */
  canTake: TraitOut[];
  /** How many the character holds, counting the cart. */
  held: number;
  /** Whether the answers have come. */
  ready: boolean;
};

/**
 * Categories a character sees only once it can take something there or holds
 * some: rituals, for a dot in a discipline with rituals or a merit that opens them.
 */
export const SHOWN_WHEN_OPEN = new Set(["rituals"]);

/**
 * What the character can take in each category, judged on the sheet as the cart
 * would leave it, so a discipline dot in the cart opens its techniques straight
 * away.
 */
export function useChoices(
  characterId: string,
  catalogue: CatalogueOut,
  categories: string[],
  held: { category: string; name: string; detail: string }[],
  lines: CartLine[],
  enabled = true,
): Choices[] {
  const planned = usePlannedUnavailable(characterId, categories, lines.map(toChange), enabled);
  return categories.map((key) => {
    const traits = catalogue.traits.filter((t) => t.category === key);
    const refused = planned.data?.[key] ?? {};
    const mine = held.filter((h) => h.category === key);
    return {
      key,
      name: catalogue.categories.find((c) => c.key === key)?.name ?? key,
      traits,
      refused,
      canTake: takeable(traits, refused, mine),
      held: mine.length,
      ready: !!planned.data,
    };
  });
}

/**
 * What "What this character can take" leaves out of a category's list. For merits
 * and flaws, only what no choice there could allow: one refused because of another
 * held stays, greyed with the reason, so unticking the other frees it. For powers,
 * what is refused now.
 */
export function useBarred(characterId: string, choices: Choices | undefined): Record<string, string> | undefined {
  const kinded = !!choices && byKind(choices.traits);
  const empty = useUnavailable(characterId, choices?.key ?? "", kinded, { asIf: "empty" });
  if (!choices?.ready) return undefined;
  return kinded ? empty.data : choices.refused;
}

/**
 * Categories to point to from the sheet: ones the character holds nothing in but
 * could take something from now. The first category is left out, as Add opens on it.
 */
export function openToYou(choices: Choices[]): Choices[] {
  return choices.slice(1).filter((c) => c.ready && c.held === 0 && c.canTake.length > 0);
}

/** The chips to show: every category, but rituals only once open (SHOWN_WHEN_OPEN). */
export function shownChips(choices: Choices[], current: string): Choices[] {
  return choices.filter((c) => c.key === current || !SHOWN_WHEN_OPEN.has(c.key) || (c.ready && (c.held > 0 || c.canTake.length > 0)));
}

/**
 * Where a search finds nothing in the current category: what it finds in the
 * others, whether the character can take it or not.
 */
export function foundElsewhere(choices: Choices[], current: string, query: string, held: { category: string; name: string; detail: string }[]) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return choices
    .filter((c) => c.key !== current)
    .flatMap((c) =>
      c.traits
        .filter((t) => t.name.toLowerCase().includes(q) && !held.some((h) => h.category === c.key && h.name === t.name && !h.detail))
        .map((t) => ({ category: c, trait: t, canTake: c.canTake.includes(t) })),
    );
}
