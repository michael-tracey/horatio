import type { FeedingIn, FeedingNeedOut } from "./api/types";

/** Herd from another character, as the receiving character's form shows it. */
export type Gift = { character_name: string; amount: number; submitted: boolean };

export const emptyFeeding = (): FeedingIn => ({
  actions: 0,
  where: "",
  herd_own: 0,
  gifts: [],
  herd_saved: 0,
  herd_other: 0,
  herd_other_text: "",
  resonance: "",
  territory: "",
  patrols: [],
});

/** The Herd dots the answer shares out, which can't be more than the rating. */
export function herdShared(answer: FeedingIn): number {
  return (
    (answer.herd_own ?? 0) +
    (answer.gifts ?? []).reduce((n, g) => n + (g.amount ?? 0), 0) +
    (answer.herd_saved ?? 0) +
    (answer.herd_other ?? 0)
  );
}

/** "You need 2 feeding this cycle: Gangrel 1 · Disease Carrier +1." */
export function needText(need: FeedingNeedOut): { needed: number; reasons: string } {
  return { needed: need.needed, reasons: need.lines.map((l) => l.text).join(" · ") };
}

export type Tally = { parts: string[]; total: number; needed: number; enough: boolean; text: string };

/**
 * The advisory tally: "Enough feeding: 4 of the 2 needed (1 feeding action, 1 from
 * your Herd, 2 from Bram) ✓", or "0 of the 1 feeding needed so far: you'll come to
 * game at half Blood…". Herd counts as the character's traits say (twice, or not
 * at all). Feeding in a territory counts for one. Nothing is blocked; storytellers decide.
 */
export function tally(need: FeedingNeedOut, answer: FeedingIn, received: Gift[], territory?: string): Tally {
  const factor = need.herd_factor;
  const actions = answer.actions ?? 0;
  const own = (answer.herd_own ?? 0) * factor;
  const parts: string[] = [];
  if (actions) parts.push(actions === 1 ? "1 feeding action" : `${actions} feeding actions`);
  if (answer.herd_own) parts.push(`${own} from your Herd`);
  for (const g of received) parts.push(`${g.amount * factor} from ${g.character_name}`);
  // With feeding territories, feeding in one stands in for a feeding action.
  if (territory) parts.push(`1 from feeding in ${territory}`);
  const total = actions + own + received.reduce((n, g) => n + g.amount * factor, 0) + (territory ? 1 : 0);
  const enough = !need.always_half && total >= need.needed;
  const from = parts.length ? ` (${parts.join(", ")})` : "";
  const text = enough
    ? `Enough feeding: ${total} of the ${need.needed} needed${from} ✓`
    : need.always_half
      ? `${total} of the ${need.needed} feeding needed${from}: no feeding brings you to full Blood, so you'll come to game at half Blood unless staff say otherwise.`
      : `${total} of the ${need.needed} feeding needed so far${from}: you'll come to game at half Blood unless staff say otherwise.`;
  return { parts, total, needed: need.needed, enough, text };
}

/**
 * The tally as staff read it on the cycle's Feeding tab: "Has 1 of the 2 feeding
 * it needs, short 1: Herd from Agnes 1". Only what counts is listed.
 */
export function staffTallyText(t: { needed: number; total: number; enough: boolean; parts: { label: string; amount: number }[] }): string {
  const counted = t.parts.filter((p) => p.amount > 0).map((p) => `${p.label === "your Herd" ? "own Herd" : p.label} ${p.amount}`);
  const from = counted.length ? `: ${counted.join(", ")}` : "";
  if (t.enough) return `Has ${t.total} feeding, enough for the ${t.needed} it needs${from} ✓`;
  if (t.total < t.needed) return `Has ${t.total} of the ${t.needed} feeding it needs, short ${t.needed - t.total}${from}`;
  return `Has ${t.total} feeding${from}, but no feeding brings it to full Blood`;
}

/** The general actions the Feeding section spends: feeding actions (none with the Rack) and, with feeding territories, patrols. */
export function feedingActionsSpent(answer: FeedingIn, rack: boolean, territories: boolean): number {
  const patrols = territories ? (answer.patrols ?? []).reduce((n, p) => n + (p.actions ?? 0), 0) : 0;
  return (rack ? 0 : (answer.actions ?? 0)) + patrols;
}
