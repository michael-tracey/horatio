/**
 * The rules of tapping dots in the creation wizard, kept apart from the screen
 * so they can be tested. A category's picks are a map of trait name to the
 * rating picked; `allowed` maps each rating to how many picks it has.
 */

import type { CatalogueOut, CategoryOut } from "../../../api/types";
import { fieldNeeded } from "../fields";

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

/** The archetype a player makes up (p. 86): its detail is the name they give it. */
export const CUSTOM_ARCHETYPE = "Other…";

/** What a choice is called: a custom archetype by the name its player gave it. */
export function choiceName(t: { category: string; name: string; detail: string }): string {
  return t.category === "archetype" && t.name === CUSTOM_ARCHETYPE && t.detail.trim() ? t.detail : t.name;
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

/**
 * A skill bought once per field can be picked more than once, a field each
 * (Performance: Singing 2 and Performance: Dance 1). The first is picked under
 * the skill's name; each other under a key of its own, from `copyKey`.
 */
const COPY = " #";

export function copyKey(name: string, n: number): string {
  return `${name}${COPY}${n}`;
}

/** The trait a pick is on, whichever of its fields it is. */
export function traitOf(key: string): string {
  const at = key.indexOf(COPY);
  return at === -1 ? key : key.slice(0, at);
}

/** The keys picked on `name`, the skill's own first. */
export function keysOf(picks: Picks, name: string): string[] {
  return Object.keys(picks)
    .filter((k) => traitOf(k) === name)
    .sort((a, b) => (a === name ? -1 : b === name ? 1 : a.localeCompare(b, undefined, { numeric: true })));
}

/** A key for one more field of `name`, not yet in use. */
export function nextCopy(taken: Iterable<string>, name: string): string {
  const used = new Set(taken);
  let n = 2;
  while (used.has(copyKey(name, n))) n++;
  return copyKey(name, n);
}

/**
 * Saved picks of one category as the wizard holds them: picks and their
 * details, by key. A skill with several fields gets a key per field, the
 * highest rated first.
 */
export function keyed(traits: { name: string; detail: string; pick: number }[]): { picks: Picks; details: Record<string, string> } {
  const picks: Picks = {};
  const details: Record<string, string> = {};
  const sorted = [...traits].sort((a, b) => a.name.localeCompare(b.name) || b.pick - a.pick || a.detail.localeCompare(b.detail));
  for (const t of sorted) {
    const key = t.name in picks ? nextCopy(Object.keys(picks), t.name) : t.name;
    picks[key] = t.pick;
    details[key] = t.detail;
  }
  return { picks, details };
}

/** What stops a pick of a skill that needs a field: no field yet, or a field another
 * pick of that skill already has (`twice`, which cannot be saved at all). */
export type FieldProblem = { message: string; twice: boolean };

export function fieldProblems(
  picks: Picks,
  details: Record<string, string>,
  needsField: (name: string) => boolean,
): Record<string, FieldProblem> {
  const problems: Record<string, FieldProblem> = {};
  const seen = new Set<string>();
  for (const key of Object.keys(picks).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))) {
    const name = traitOf(key);
    if (!needsField(name)) continue;
    const field = (details[key] ?? "").trim();
    const known = `${name}/${field.toLowerCase()}`;
    if (!field) problems[key] = { message: `${fieldNeeded(name)}.`, twice: false };
    else if (seen.has(known)) problems[key] = { message: `${name}: ${field} is picked already; give this one another field.`, twice: true };
    seen.add(known);
  }
  return problems;
}
