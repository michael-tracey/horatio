/**
 * The rules of tapping dots in the creation wizard, kept apart from the screen
 * so they can be tested. A category's picks are a map of trait name to the
 * rating picked; `allowed` maps each rating to how many picks it has.
 */

export type Picks = Record<string, number>;
export type Allowed = Record<number, number>;

export function used(picks: Picks, rating: number): number {
  return Object.values(picks).filter((r) => r === rating).length;
}

export function left(picks: Picks, allowed: Allowed, rating: number): number {
  return (allowed[rating] ?? 0) - used(picks, rating);
}

/** Whether tapping `rating` on `name` would do anything. */
export function canTap(picks: Picks, allowed: Allowed, name: string, rating: number): boolean {
  if (!(rating in allowed)) return false;
  if (picks[name] === rating) return true;
  return left(picks, allowed, rating) > 0 || allowed[rating] === 1;
}

/**
 * Tap a dot. Tapping a trait's current rating clears it. Tapping a rating with
 * picks left sets it. Tapping a rating whose only pick another trait holds
 * swaps the two (so Physical 7 / Mental 3 becomes Mental 7 / Physical 3).
 * Anything else leaves the picks as they were.
 */
export function tap(picks: Picks, allowed: Allowed, name: string, rating: number): Picks {
  if (!(rating in allowed)) return picks;
  const next = { ...picks };
  if (picks[name] === rating) {
    delete next[name];
    return next;
  }
  if (left(picks, allowed, rating) > 0) {
    next[name] = rating;
    return next;
  }
  if (allowed[rating] === 1) {
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
