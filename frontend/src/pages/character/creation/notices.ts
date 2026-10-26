/**
 * Cross-step notices (#192): when something taken on one step of the wizard
 * changes another, each step it touches says so, the stepper marks it, and Review
 * lists it, linking to the step where it is put right.
 *
 * Notices are worked out from what the server already says (the creation pools,
 * and the checks the sheet breaks, with what each looks at), never from a second
 * copy of the rules. Each kind comes from a `NoticeSource`; a step that needs a new
 * kind adds a source to the wizard's list.
 */

import type { CreationOut, SheetOut } from "../../../api/types";

/** A wizard step as notices see it: the categories it places picks in, and those it
 * decides without picks (Concept: the clan, and the extra in-clan disciplines). */
export type StepRef = { key: string; title: string; categories: string[]; decides?: string[] };

export type StepNotice = {
  key: string;
  message: string;
  /** The steps that show it, in wizard order. */
  on: string[];
  /** Where it is put right: the step its link goes to. */
  fix: string;
  /** The trait it is about, on the fix step, for that step to mark. */
  trait?: { category: string; name: string };
};

export type NoticeInput = { creation: CreationOut; sheet: SheetOut; steps: StepRef[] };
export type NoticeSource = (input: NoticeInput) => StepNotice[];

/** The step that places or decides a category. */
export function stepFor(steps: StepRef[], category: string): StepRef | undefined {
  return steps.find((s) => s.categories.includes(category) || s.decides?.includes(category));
}

/** Step keys in wizard order, each once, leaving out any the wizard does not have. */
export function inOrder(steps: StepRef[], keys: (string | undefined)[]): string[] {
  const wanted = new Set(keys.filter((k): k is string => !!k));
  return steps.filter((s) => wanted.has(s.key)).map((s) => s.key);
}

/** Where a pool's restriction is decided: "in_clan" by the clan and the merits on Concept. */
const DECIDED_ON: Record<string, string> = { in_clan: "concept" };
const RESTRICTION_WORDS: Record<string, string> = { in_clan: "in-clan" };

/**
 * Picks kept where they no longer fit (rule 4): a starting dot on a discipline that
 * is no longer in-clan. Shown where it was placed, and where the change was made.
 */
export const strayPicks: NoticeSource = ({ creation, steps }) =>
  creation.pools.flatMap((pool) =>
    pool.traits
      .filter((t) => !t.fits && pool.restriction)
      .map((t): StepNotice | null => {
        const placed = stepFor(steps, pool.category)?.key;
        if (!placed) return null;
        const dots = pool.rating === 1 ? "dot" : "dots";
        const words = RESTRICTION_WORDS[pool.restriction!] ?? pool.restriction!;
        return {
          key: `stray/${pool.category}/${t.name}/${t.detail}`,
          message: `Your starting ${dots} in ${t.name} ${pool.rating === 1 ? "needs" : "need"} moving: it is no longer ${words}.`,
          on: inOrder(steps, [DECIDED_ON[pool.restriction!], placed]),
          fix: placed,
          trait: { category: pool.category, name: t.name },
        };
      })
      .filter((n): n is StepNotice => n !== null),
  );

/**
 * Checks the sheet breaks that finishing needs settled (or that refuse outright),
 * on the steps of the trait they are about and of every trait they look at:
 * "Vestiges of Greatness: choose one of your in-clan disciplines from…" on Merits
 * and on Concept. Put right on the earliest of them. One the wizard already holds
 * a step to (a need, such as Generation on Backgrounds) is left to that step.
 */
export const brokenChecks: NoticeSource = ({ creation, sheet, steps }) => {
  const needs = new Set(creation.needs.map((n) => n.message));
  const found = new Map<string, StepNotice>();
  for (const problem of sheet.problems) {
    if (problem.strength !== "refuse" && problem.strength !== "complete") continue;
    const on = inOrder(steps, [stepFor(steps, problem.category)?.key, ...(problem.looks_at ?? []).map((t) => stepFor(steps, t.category)?.key)]);
    if (!on.length || found.has(problem.message) || needs.has(problem.message)) continue;
    found.set(problem.message, { key: `check/${problem.message}`, message: problem.message, on, fix: on[0]! });
  }
  return [...found.values()];
};

/** Every notice open now, from `sources`; one per message. */
export function stepNotices(input: NoticeInput, sources: NoticeSource[]): StepNotice[] {
  const seen = new Set<string>();
  return sources
    .flatMap((source) => source(input))
    .filter((n) => {
      if (seen.has(n.message)) return false;
      seen.add(n.message);
      return true;
    });
}
