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
 * The advisory tally: "Feeding 1 + your Herd 1 + 2 from Bram = 4 of 2 needed ✓".
 * Herd counts as the character's traits say (twice, or not at all). Nothing is
 * blocked; storytellers decide.
 */
export function tally(need: FeedingNeedOut, answer: FeedingIn, received: Gift[]): Tally {
  const factor = need.herd_factor;
  const own = (answer.herd_own ?? 0) * factor;
  const parts = [`Feeding ${answer.actions ?? 0}`];
  if (answer.herd_own) parts.push(`your Herd ${own}`);
  for (const g of received) parts.push(`${g.amount * factor} from ${g.character_name}`);
  const total = (answer.actions ?? 0) + own + received.reduce((n, g) => n + g.amount * factor, 0);
  const enough = !need.always_half && total >= need.needed;
  const sum = `${parts.join(" + ")} = ${total} of ${need.needed} needed`;
  const text = enough
    ? `${sum} ✓`
    : need.always_half
      ? `${sum}: no feeding brings you to full Blood, so you'll come to game at half Blood unless staff say otherwise.`
      : `${sum}: you'll come to game at half Blood unless staff say otherwise.`;
  return { parts, total, needed: need.needed, enough, text };
}
