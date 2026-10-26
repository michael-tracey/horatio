/**
 * The wizard for a ghoul (MET: VTM p. 296): no clan of its own, but its domitor's,
 * chosen on Concept; and 5 discipline dots, in the domitor's in-clan disciplines,
 * any left unplaced saved for later. The rest is a vampire's, less what the ghoul
 * rule set leaves out (Generation, Morality), which the server's pools and checks
 * already say.
 */

import type { CreationOut, PoolOut } from "../../../api/types";
import { inOrder, type NoticeSource } from "./notices";

/** Categories whose points are dots to share out, as many on a trait as it likes (a
 * ghoul's 5 discipline dots), not traits ticked at their own value (merits). */
const DOT_BUDGETS = ["disciplines"];

/** A category's budget of dots to share out, if it has one: a ghoul's disciplines. */
export function dotBudget(creation: CreationOut, category: string): PoolOut | undefined {
  return DOT_BUDGETS.includes(category) ? creation.pools.find((p) => p.category === category && p.kind === "points") : undefined;
}

/** Finishing needs the domitor, and the ghoul's disciplines wait on it. */
export const domitorNeeded: NoticeSource = ({ ghoul, steps }) =>
  ghoul && !ghoul.domitor
    ? [{ key: "ghoul/domitor", message: "Choose the domitor: a ghoul's clan and in-clan disciplines are its domitor's.", on: inOrder(steps, ["concept", "disciplines"]), fix: "concept" }]
    : [];

/** The Disciplines step for a ghoul, in words: what its dots go on, and what happens to those left. */
export function ghoulDisciplinesIntro(pool: PoolOut, linked: boolean): string {
  const cap = linked ? ", no higher than your domitor has each" : "";
  return `A ghoul has ${pool.allowed} dots of disciplines, all in its domitor's in-clan disciplines${cap}. Put as many on one as you like.`;
}

/** What the ghoul's `saved` unplaced dots come to, in words; null for none. */
export function savedDots(saved: number): string | null {
  if (saved <= 0) return null;
  return `${saved} ${saved === 1 ? "dot is" : "dots are"} saved for later. They are kept after creation, and placed later the same way: in the domitor's in-clan disciplines.`;
}
