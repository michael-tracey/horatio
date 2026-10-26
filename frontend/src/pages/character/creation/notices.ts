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

/** The in-clan disciplines a character chooses, decided on Concept (see inClan.ts). */
export const EXTRA_IN_CLAN = "extra_in_clan_disciplines";

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
  /** It is an in-clan choice still to make: the steps that offer the choice themselves (Merits, Disciplines, Review) say so. */
  inClan?: boolean;
  /** Finishing does not wait on it (a merit's free traits, chosen until a troupe accepts). */
  canWait?: boolean;
};

/** `ghoul` for a ghoul, whose clan and in-clan disciplines are its domitor's: whether it has one yet. */
export type NoticeInput = { creation: CreationOut; sheet: SheetOut; steps: StepRef[]; ghoul?: { domitor: boolean } };
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

/** Names in a sentence: "A, B and C". */
export function listed(names: string[]): string {
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : (names[0] ?? "");
}

/** The traits a pool, or a pick, is because of, by name: "Thin Blooded". */
const causes = (refs: { name?: string | null }[]): string[] => [...new Set(refs.map((r) => r.name).filter((n): n is string => !!n))];

/** Where a pool's restriction is decided: "in_clan" by the clan and the merits on Concept. */
const DECIDED_ON: Record<string, string> = { in_clan: "concept" };
const RESTRICTION_WORDS: Record<string, string> = { in_clan: "in-clan" };

/**
 * Picks kept where they no longer fit (rule 4): a starting dot on a discipline that
 * is no longer in-clan, or that a merit or flaw leaves without a free dot (Inept).
 * Shown where it was placed, and where the change was made.
 */
export const strayPicks: NoticeSource = ({ creation, steps }) =>
  creation.pools.flatMap((pool) =>
    pool.traits
      .filter((t) => !t.fits && pool.restriction)
      .map((t): StepNotice | null => {
        const placed = stepFor(steps, pool.category)?.key;
        if (!placed) return null;
        const dots = pool.rating === 1 ? "dot" : "dots";
        const needs = pool.rating === 1 ? "needs" : "need";
        const words = RESTRICTION_WORDS[pool.restriction!] ?? pool.restriction!;
        const because = causes(t.because);
        return {
          key: `stray/${pool.category}/${t.name}/${t.detail}`,
          message: because.length
            ? `${listed(because)}: ${t.name} starts without a free dot, so your starting ${dots} in it ${needs} moving.`
            : `Your starting ${dots} in ${t.name} ${needs} moving: it is no longer ${words}.`,
          on: inOrder(steps, [because.length ? undefined : DECIDED_ON[pool.restriction!], ...t.because.map((b) => stepFor(steps, b.category)?.key), placed]),
          fix: placed,
          trait: { category: pool.category, name: t.name },
        };
      })
      .filter((n): n is StepNotice => n !== null),
  );

/**
 * More picks than the rules give now (rule 4): Thin Blooded takes away the pick at 2,
 * and Inept one pick at 1, once the starting dots are placed. The picks are kept, and
 * the step and the one that changed it say which need moving.
 */
export const overBudget: NoticeSource = ({ creation, steps }) =>
  creation.pools
    .filter((pool) => pool.kind === "picks" && pool.remaining < 0)
    .map((pool): StepNotice | null => {
      const placed = stepFor(steps, pool.category)?.key;
      if (!placed) return null;
      const because = causes(pool.because);
      const who = because.length ? listed(because) : "The rules";
      const what = pool.category_name.toLowerCase();
      const picked = listed(pool.traits.map((t) => t.name));
      const message = pool.allowed
        ? `${who}: starting ${what} have ${pool.allowed} ${pool.allowed === 1 ? "pick" : "picks"} at ${pool.rating} now, and ${pool.used} are placed. Take ${-pool.remaining} back.`
        : `${who}: starting ${what} no longer have a pick at ${pool.rating}. Your dot in ${picked} needs moving.`;
      return {
        key: `over/${pool.category}/${pool.rating}`,
        message,
        on: inOrder(steps, [placed, ...pool.because.map((b) => stepFor(steps, b.category)?.key)]),
        fix: placed,
        trait: pool.traits.length === 1 ? { category: pool.category, name: pool.traits[0]!.name } : undefined,
      };
    })
    .filter((n): n is StepNotice => n !== null);

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
    // A clash (a check that refuses) names the pick it is with: "Archaic and Computer
    // clash: …". A need the player must meet (Vestiges: choose one) keeps its own words.
    const clashing = sheet.traits.filter(
      (t) =>
        problem.strength === "refuse" &&
        (t.rating ?? 0) > 0 &&
        !(t.category === problem.category && t.name === problem.name) &&
        (problem.looks_at ?? []).some((l) => l.category === t.category && (l.name == null || l.name === t.name)) &&
        stepFor(steps, t.category)?.key !== stepFor(steps, problem.category)?.key,
    );
    const names = [...new Set(clashing.map((t) => t.name))];
    const message = names.length ? `${problem.name} and ${listed(names)} clash: ${problem.message}` : problem.message;
    // Vestiges of Greatness wanting one from the uncommon list: a choice of in-clan disciplines.
    const inClan = problem.strength === "complete" && (problem.looks_at ?? []).some((t) => t.category === EXTRA_IN_CLAN);
    found.set(problem.message, { key: `check/${problem.message}`, message, on, fix: on[0]!, ...(inClan ? { inClan } : {}) });
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
