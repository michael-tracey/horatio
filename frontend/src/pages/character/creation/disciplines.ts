/**
 * The Disciplines step (#192): what changes its budget and its choices, and is taken
 * from the step as well as from Merits & flaws. What the character can take, and
 * what each does to the pools, is the server's to say; this lists the traits to offer,
 * and words the budget the pools give now.
 */

import type { CreationOut, PoolOut } from "../../../api/types";
import { listed } from "./notices";

/** Flaws that change the starting disciplines: Thin Blooded's budget, and the discipline Inept names. */
export const DISCIPLINE_FLAWS = ["Thin Blooded", "Inept"];

/** Merits that open a discipline (Training, Setite Sorcery, Premascine) or price a path in-clan. */
export const BLOOD_MAGIC_MERITS = [
  "Thaumaturgic Training",
  "Necromantic Training",
  "Setite Sorcery",
  "Bloodline: Premascine",
  "Thaumaturgic Expertise",
  "Necromantic Expertise",
  "Necromantic Insight",
  "Chosen of the Crone",
  "Bloodline: Koldun",
  "Bloodline: Sorcerer",
];

export const INEPT = "Inept";

export const DISCIPLINES_FROM_MERITS = [
  ...BLOOD_MAGIC_MERITS.map((name) => ({ category: "merits", name })),
  ...DISCIPLINE_FLAWS.map((name) => ({ category: "flaws", name })),
];

const NUMBERS = ["no", "one", "two", "three", "four", "five", "six"];
const number = (n: number) => NUMBERS[n] ?? String(n);

/** The pools of starting picks a category gives now. */
function startingPools(creation: CreationOut, category: string): PoolOut[] {
  return creation.pools.filter((p) => p.category === category && p.kind === "picks" && p.allowed > 0).sort((a, b) => b.rating - a.rating);
}

/** The Disciplines step's budget in words, as the pools give it now: Thin Blooded and Inept change it. */
export function disciplinesIntro(creation: CreationOut): string {
  const pools = startingPools(creation, "disciplines");
  if (!pools.length) return "";
  const budget = listed(pools.map((p) => `${number(p.allowed)} at ${p.rating}`));
  const changedBy = [...new Set(creation.budget_changes.filter((c) => c.category === "disciplines").flatMap((c) => c.because.map((b) => b.name).filter((n): n is string => !!n)))];
  const why = changedBy.length ? ` (${listed(changedBy)} changes the usual)` : "";
  return `Starting disciplines are your in-clan ones: ${budget}${why}.`;
}

/** Why each discipline that takes no free starting dot takes none, by name. */
export function withoutDotReasons(creation: CreationOut, category: string): Record<string, string> {
  const found: Record<string, string> = {};
  for (const pool of creation.pools.filter((p) => p.category === category))
    for (const entry of pool.without_dot) {
      const by = [...new Set(entry.because.map((b) => b.name).filter((n): n is string => !!n))];
      found[entry.name] = `${by.length ? `${listed(by)}: ` : ""}${entry.name} starts without a free dot.`;
    }
  return found;
}

/** The in-clan disciplines Inept can name now, and the one it names if it is held. */
export function ineptChoices(creation: CreationOut, held?: string): string[] {
  const options = creation.pools.find((p) => p.category === "disciplines" && p.restriction === "in_clan")?.options ?? [];
  return [...new Set([...options, ...(held ? [held] : [])])].sort();
}
