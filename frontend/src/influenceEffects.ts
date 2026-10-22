/**
 * Targeted influence actions and what they do (backend: horatio.influence_effects).
 * An Attack lowers a rating for two games or a month, whichever is later; a Boost
 * raises one to the end of the month; a Block makes an activity cost more.
 */
import type { Dates } from "./dates";

/** The actions logged with a target. */
export const TARGETED = ["attack", "block", "boost", "defend"] as const;

export function targeted(actionKey: string | null | undefined): boolean {
  return (TARGETED as readonly string[]).includes(actionKey ?? "");
}

function games(n: number): string {
  return n === 1 ? "1 more game" : `${n} more games`;
}

/** How long an effect lasts: "until 21 Nov 2026", "until 21 Nov 2026, or 2 more games if that is later", "until 1 more game is played". */
export function lastsText(effect: { ends_at: string; games_left: number }, dates: Pick<Dates, "date">, now: Date = new Date()): string {
  const dated = new Date(effect.ends_at) > now;
  if (!effect.games_left) return `until ${dates.date(effect.ends_at)}`;
  if (!dated) return `until ${games(effect.games_left)} ${effect.games_left === 1 ? "is" : "are"} played`;
  return `until ${dates.date(effect.ends_at)}, or ${games(effect.games_left)} if that is later`;
}

/** What resolving would cost, as staff weigh it: "2 levels at 2 actions each: 4 actions. E3 spent 4." */
export function costText(plan: { kind: string; levels: number; cost: number; per_level: number; spent: number }, shortId: string): string {
  const levels = plan.levels === 1 ? "1 level" : `${plan.levels} levels`;
  if (plan.kind === "block") return `Strength ${plan.levels}.`;
  const each = plan.kind === "attack" ? ` at ${plan.per_level} actions each` : "";
  return `${levels}${each}: ${plan.cost} ${plan.cost === 1 ? "action" : "actions"}. ${shortId} spent ${plan.spent}.`;
}
