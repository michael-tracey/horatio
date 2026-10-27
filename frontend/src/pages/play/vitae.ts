import type { PlayView } from "../../api/types";

/**
 * A ghoul's Blood (MET: VtM core p. 297): 10 in all, of which up to 5 is vampiric
 * vitae, which `blood` counts and which can be spent; the rest is human Blood, which
 * cannot. Vitae refills only by drinking it, and a ghoul must drink every month: after
 * that it ages 10 years a day until it drinks.
 */

/** Each box of the pool, in order: vitae to spend, then human Blood, then spent. */
export type PoolBox = "vitae" | "human" | "spent";

export function poolBoxes(view: Pick<PlayView, "blood" | "vitae">): PoolBox[] {
  const vitae = view.vitae;
  if (!vitae) return [];
  const human = Math.min(vitae.human, vitae.pool - view.blood.value);
  return [
    ...Array<PoolBox>(view.blood.value).fill("vitae"),
    ...Array<PoolBox>(Math.max(0, human)).fill("human"),
    ...Array<PoolBox>(Math.max(0, vitae.pool - view.blood.value - human)).fill("spent"),
  ];
}

/** How much a drink can add: up to the most vitae, at least 1 (a drink to keep the month). */
export function drinkMost(view: Pick<PlayView, "blood">): number {
  return Math.max(1, view.blood.most - view.blood.value);
}

const DAY = 24 * 60 * 60 * 1000;

export type Reminder = { level: "ok" | "near" | "over"; text: string };

/**
 * The monthly drink, keyed to the last one: how long ago it was, a warning in the
 * last week of the month, and once the month is up, what that does.
 */
export function drinkReminder(lastDrankAt: string | null, days: number, now: Date = new Date()): Reminder {
  if (!lastDrankAt) return { level: "near", text: `No drink of vitae recorded yet. A ghoul must drink every month (${days} days), or it ages 10 years a day until it does.` };
  const since = Math.floor((now.getTime() - Date.parse(lastDrankAt)) / DAY);
  const ago = since <= 0 ? "today" : since === 1 ? "yesterday" : `${since} days ago`;
  const left = days - since;
  if (left <= 0) return { level: "over", text: `Last drank vitae ${ago}. Over a month without it: the ghoul ages 10 years a day until it drinks, and dies at a relative age of 100 (p. 297).` };
  if (left <= 7) return { level: "near", text: `Last drank vitae ${ago}. Drink within ${left === 1 ? "1 day" : `${left} days`}, or start to age 10 years a day.` };
  return { level: "ok", text: `Last drank vitae ${ago}.` };
}
