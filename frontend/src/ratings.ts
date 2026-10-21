/** Ratings as numbers or as pips (Settings → Show ratings as), on screen and on paper alike. */

import type { Preferences } from "./api/types";

export type Ratings = Preferences["ratings"];

/** A pip: held, held but awaiting approval, empty, or one a change in the cart would add or take away. */
export type Pip = "held" | "waiting" | "empty" | "planned";

/** How many pips a category's ratings show at least: attributes run to ten, the rest to five, as on the paper sheet. */
export function pipsOf(category: string): number {
  return category === "attributes" ? 10 : 5;
}

/**
 * A rating's pips in groups of five, like the paper sheet: `value` filled, then
 * empty ones up to `of` (more pips if the rating goes past it). Pips from
 * `pendingFrom` up are still awaiting approval. With `planned`, the rating a
 * change in the cart would make it, the pips between the two are planned ones:
 * those it would add, or those it would take away.
 */
export function pipGroups(value: number, of = 5, pendingFrom: number | null = null, planned: number | null = null): Pip[][] {
  const held = pendingFrom != null && pendingFrom < value ? pendingFrom : value;
  const low = planned == null ? value : Math.min(value, planned);
  const high = planned == null ? value : Math.max(value, planned);
  const pips = Array.from({ length: Math.max(of, high) }, (_, i): Pip => (i >= low && i < high ? "planned" : i < held ? "held" : i < value ? "waiting" : "empty"));
  return Array.from({ length: Math.ceil(pips.length / 5) }, (_, g) => pips.slice(g * 5, g * 5 + 5));
}

/** How a printed sheet shows ratings: as `?ratings=` asks, for one print, else as the person's setting. */
export function printedRatings(asked: string | null, setting: Ratings): Ratings {
  return asked === "numbers" || asked === "pips" ? asked : setting;
}
