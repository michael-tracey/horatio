/**
 * The rules of placing picks in the creation wizard, kept apart from the screen
 * so they can be tested. A category's picks are a map of trait name to the
 * rating picked; `allowed` maps each rating to how many picks it has.
 */

import type { CatalogueOut, CategoryOut } from "../../../api/types";
import type { DetailNeed } from "../fields";

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
 * attributes' 7 / 5 / 3 or a single focus.
 */
export function isRanking(allowed: Allowed): boolean {
  return Object.values(allowed).every((n) => n === 1);
}

/** Take `name`'s pick back, whatever its rating. */
export function clear(picks: Picks, name: string): Picks {
  if (!(name in picks)) return picks;
  const next = { ...picks };
  delete next[name];
  return next;
}

/**
 * Choose `name` for a slot at `rating`, in place of `holder` (the pick in the slot
 * now, if any). A trait picked at another rating moves (see `move`), so in a ranking
 * Physical 7 / Mental 3 becomes Mental 7 / Physical 3. A skill bought once per field
 * (`fielded`) can be chosen again, for another field, under a key of its own.
 * Anything that does not fit leaves the picks as they were. Gives the picks, and the
 * key now in the slot.
 */
export function choose(
  picks: Picks,
  allowed: Allowed,
  rating: number,
  holder: string | null,
  name: string,
  fielded = false,
): { picks: Picks; key: string | null } {
  const unchanged = { picks, key: holder };
  if (!(rating in allowed)) return unchanged;
  if (holder !== null && traitOf(holder) === name) return unchanged;
  if (!fielded && name in picks && picks[name] !== rating) return move(picks, allowed, rating, holder, name);
  const next = holder === null ? { ...picks } : clear(picks, holder);
  if (name in next && !fielded) return unchanged;
  if (left(next, allowed, rating) <= 0) return unchanged;
  const key = name in next ? nextCopy(Object.keys(next), name) : name;
  next[key] = rating;
  return { picks: next, key };
}

/** What became of the pick a move took the slot of: gone to the slot the move left, or taken off. */
export type Moved = { picks: Picks; key: string | null; holder: "swapped" | "off" | null };

/**
 * Move the pick `key`, placed at another rating, to a slot at `rating`, in place of
 * `holder` (the pick in the slot now, if any). The holder takes the slot the move
 * left when it fits there (`fits`: not barred at that rating, say), a swap; if not,
 * it is taken off, and that slot is left empty. Each pick keeps its key, so a skill's
 * field moves with it. Anything that does not fit leaves the picks as they were.
 */
export function move(
  picks: Picks,
  allowed: Allowed,
  rating: number,
  holder: string | null,
  key: string,
  fits: (name: string, rating: number) => boolean = () => true,
): Moved {
  const from = picks[key];
  const unchanged: Moved = { picks, key: holder, holder: null };
  if (from === undefined || from === rating || holder === key || !(rating in allowed)) return unchanged;
  const next = { ...picks };
  delete next[key];
  if (holder !== null) delete next[holder];
  if (left(next, allowed, rating) <= 0) return unchanged;
  next[key] = rating;
  if (holder === null) return { picks: next, key, holder: null };
  if (left(next, allowed, from) > 0 && fits(traitOf(holder), from)) {
    next[holder] = from;
    return { picks: next, key, holder: "swapped" };
  }
  return { picks: next, key, holder: "off" };
}

/**
 * The picks at one rating laid out in its `slots`, each kept in the slot it was
 * in (`seated`, the last layout) so choosing one doesn't shuffle the others. New
 * picks take the first empty slots; picks beyond the slots (more than the rules give
 * now) come after them, to be moved.
 */
export function seatPicks(seated: (string | null)[], keys: string[], slots: number): (string | null)[] {
  const kept = seated.map((k) => (k !== null && keys.includes(k) ? k : null));
  const out: (string | null)[] = kept.slice(0, slots);
  while (out.length < slots) out.push(null);
  const rest = [...kept.slice(slots).filter((k): k is string => k !== null), ...keys.filter((k) => !kept.includes(k))];
  for (const key of rest) {
    const free = out.indexOf(null);
    if (free === -1) out.push(key);
    else out[free] = key;
  }
  return out;
}

const NUMBERS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];

/** What is left to place, in words: "3 picks left: one at 4 and two at 1", or null when nothing is. */
export function picksLeft(picks: Picks, allowed: Allowed): string | null {
  const open = Object.keys(allowed)
    .map(Number)
    .sort((a, b) => b - a)
    .map((rating) => [rating, left(picks, allowed, rating)] as const)
    .filter(([, n]) => n > 0);
  if (!open.length) return null;
  const total = open.reduce((sum, [, n]) => sum + n, 0);
  const parts = open.map(([rating, n]) => `${NUMBERS[n] ?? n} at ${rating}`);
  const words = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}` : parts[0];
  return `${total} ${total === 1 ? "pick" : "picks"} left: ${words}`;
}

/**
 * Dots shared out from one budget, as many on a trait as it likes (a ghoul's 5
 * discipline dots): a tap sets the trait to that rating if the dots it adds are
 * left. Tapping the rating it has clears it.
 */
export function canTapDots(picks: Picks, budget: number, name: string, rating: number): boolean {
  return picks[name] === rating || spent(picks) - (picks[name] ?? 0) + rating <= budget;
}

export function tapDots(picks: Picks, budget: number, name: string, rating: number): Picks {
  if (picks[name] === rating) return clear(picks, name);
  if (!canTapDots(picks, budget, name, rating)) return picks;
  return { ...picks, [name]: rating };
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

/**
 * A budget of points as the wizard says it: "3 of 7 points", or for flaws taken past
 * it, which give nothing more (p. 85), "9 points, 7 XP paid out".
 */
export function pointsText(used: number, allowed: number, pastBudget: boolean): string {
  return pastBudget && used > allowed ? `${used} points, ${allowed} XP paid out` : `${used} of ${allowed} points`;
}

/** What a budget its picks may go past (flaws) says beside it (p. 85). */
export function pastBudgetText(title: string, allowed: number): string {
  return `${title} past ${allowed} points need the Storyteller's OK, and give no more XP (p. 85).`;
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

/** What stops a pick of a trait that needs a detail (a skill's field, a Retainer's
 * name): none yet, or one another pick of that trait already has (`twice`, which
 * cannot be saved at all). */
export type FieldProblem = { message: string; twice: boolean };

export function fieldProblems(
  picks: Picks,
  details: Record<string, string>,
  needs: (name: string) => DetailNeed | null,
): Record<string, FieldProblem> {
  const problems: Record<string, FieldProblem> = {};
  const seen = new Set<string>();
  for (const key of Object.keys(picks).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))) {
    const name = traitOf(key);
    const need = needs(name);
    if (!need) continue;
    const field = (details[key] ?? "").trim();
    const known = `${name}/${field.toLowerCase()}`;
    if (!field) problems[key] = { message: `${need.missing}.`, twice: false };
    else if (seen.has(known)) problems[key] = { message: `${name}: ${field} is picked already; give this one another ${need.kind}.`, twice: true };
    seen.add(known);
  }
  return problems;
}
