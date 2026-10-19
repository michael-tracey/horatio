/**
 * The rules of tapping dots in the creation wizard, kept apart from the screen
 * so they can be tested. A category's picks are a map of trait name to the
 * rating picked; `allowed` maps each rating to how many picks it has.
 */

import type { CatalogueOut, CategoryOut } from "../../../api/types";

export type Picks = Record<string, number>;
export type Allowed = Record<number, number>;

export function used(picks: Picks, rating: number): number {
  return Object.values(picks).filter((r) => r === rating).length;
}

export function left(picks: Picks, allowed: Allowed, rating: number): number {
  return (allowed[rating] ?? 0) - used(picks, rating);
}

/**
 * Whether the picks rank the traits: every rating has exactly one pick, as
 * attributes' 7 / 5 / 3 or a single focus. Only a ranking swaps; elsewhere
 * (skills' one 4, two 3s…) a used-up rating is simply used up.
 */
export function isRanking(allowed: Allowed): boolean {
  return Object.values(allowed).every((n) => n === 1);
}

/** Whether tapping `rating` on `name` would do anything. */
export function canTap(picks: Picks, allowed: Allowed, name: string, rating: number): boolean {
  if (!(rating in allowed)) return false;
  if (picks[name] === rating) return true;
  return left(picks, allowed, rating) > 0 || isRanking(allowed);
}

/** Take `name`'s pick back, whatever its rating. */
export function clear(picks: Picks, name: string): Picks {
  if (!(name in picks)) return picks;
  const next = { ...picks };
  delete next[name];
  return next;
}

/**
 * Tap a dot. Tapping a trait's current rating clears it. Tapping a rating with
 * picks left sets it. In a ranking, tapping a rating another trait holds swaps
 * the two (so Physical 7 / Mental 3 becomes Mental 7 / Physical 3). Anything
 * else leaves the picks as they were.
 */
export function tap(picks: Picks, allowed: Allowed, name: string, rating: number): Picks {
  if (!(rating in allowed)) return picks;
  const next = { ...picks };
  if (picks[name] === rating) return clear(picks, name);
  if (left(picks, allowed, rating) > 0) {
    next[name] = rating;
    return next;
  }
  if (isRanking(allowed)) {
    const holder = Object.keys(picks).find((n) => picks[n] === rating)!;
    const mine = picks[name];
    if (mine === undefined) delete next[holder];
    else next[holder] = mine;
    next[name] = rating;
    return next;
  }
  return picks;
}

/** Merits and flaws: toggle a trait worth `points` against a budget. */
export function togglePoints(picks: Picks, budget: number, name: string, points: number): Picks {
  const next = { ...picks };
  if (name in next) {
    delete next[name];
    return next;
  }
  const spent = Object.values(picks).reduce((a, b) => a + b, 0);
  if (spent + points > budget) return picks;
  next[name] = points;
  return next;
}

export function spent(picks: Picks): number {
  return Object.values(picks).reduce((a, b) => a + b, 0);
}

/** The unrated choices (clan, sect…) to offer, leaving out any whose
 * requirement the sheet does not meet: faction only for the Sabbat. */
export function identityChoices(catalogue: CatalogueOut, sheet: { traits: { category: string; name: string }[] }): CategoryOut[] {
  return catalogue.categories.filter(
    (c) =>
      !c.rated &&
      catalogue.traits.some((t) => t.category === c.key) &&
      (!c.requires || sheet.traits.some((t) => t.category === c.requires!.category && t.name === c.requires!.name)),
  );
}
