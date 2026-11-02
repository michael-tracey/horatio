/** A troupe's house rules for Retainers (issue #442): upkeep and growth, each off unless switched on. */

import type { RetainerRulesIn, RetainerRulesOut, UpkeepRule } from "../../api/types";

/** The form's state: each rule on or off, with its figures kept while off so switching back keeps them. */
export type RulesDraft = {
  upkeepOn: boolean;
  upkeep: UpkeepRule;
  growthOn: boolean;
  growth: number;
};

export const DEFAULT_UPKEEP: UpkeepRule = { amount: 1, pool: "blood", ghouls_only: false, per: "game", month_at: "game" };
export const DEFAULT_GROWTH = 4;
export const MOST_UPKEEP = 10;
export const MOST_GROWTH = 20;

export function draftOf(rules: RetainerRulesOut): RulesDraft {
  return {
    upkeepOn: !!rules.upkeep,
    upkeep: rules.upkeep ?? DEFAULT_UPKEEP,
    growthOn: !!rules.growth,
    growth: rules.growth ?? DEFAULT_GROWTH,
  };
}

/** What is saved: a rule switched off is left out, and a game's upkeep has no month to choose. */
export function bodyOf(draft: RulesDraft): RetainerRulesIn {
  const upkeep = draft.upkeep;
  return {
    upkeep: draft.upkeepOn ? { ...upkeep, month_at: upkeep.per === "month" ? upkeep.month_at : "game" } : null,
    growth: draft.growthOn ? draft.growth : null,
  };
}

/** Why the draft can't be saved, or null when it can. */
export function draftProblem(draft: RulesDraft): string | null {
  const whole = (n: number, most: number) => Number.isInteger(n) && n >= 1 && n <= most;
  if (draft.upkeepOn && !whole(draft.upkeep.amount, MOST_UPKEEP)) return `Upkeep is from 1 to ${MOST_UPKEEP} for each Retainer.`;
  if (draft.growthOn && !whole(draft.growth, MOST_GROWTH)) return `Growth is from 1 to ${MOST_GROWTH} XP a month.`;
  return null;
}
