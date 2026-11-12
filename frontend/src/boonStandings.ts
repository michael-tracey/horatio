import type { BoonStandingsOut, BoonWeightsIn } from "./api/types";
import { KINDS } from "./boons";

/** Boon standings (#691): who is counted, as the page's switch says. */
export type Scope = BoonStandingsOut["scope"];

export const SCOPES: { value: Scope; label: string; meaning: string }[] = [
  { value: "active", label: "Active", meaning: "Leaves out boons that involve someone dead or off-field." },
  { value: "everyone", label: "Everyone", meaning: "Counts every standing boon, those of the departed too." },
];

/** What each kind weighs unless the troupe sets its own. */
export const DEFAULT_WEIGHTS: BoonWeightsIn = { trivial: 0.5, minor: 1, major: 3, blood: 5, life: 10 };

/** A weight or a sum of them, as short as it goes: 3, 1.5, 0.25. */
export function weight(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
}

/** A net, signed: +2, −1.5 (a true minus sign), 0. */
export function net(value: number): string {
  if (value === 0) return "0";
  return value > 0 ? `+${weight(value)}` : `−${weight(-value)}`;
}

/** Words for a net, for a screen reader or a tooltip. */
export function netWords(value: number): string {
  if (value === 0) return "even";
  return value > 0 ? `owed ${weight(value)} more than they owe` : `owes ${weight(-value)} more than they're owed`;
}

/** A bar's length, as a share of the longest, from 0 to 100. */
export function share(value: number, most: number): number {
  if (most <= 0 || value <= 0) return 0;
  return Math.min(100, (100 * value) / most);
}

/** The weights as a line: "Trivial 0.5 · Minor 1 · …". */
export function weightsLine(weights: BoonWeightsIn): string {
  return KINDS.map((k) => `${k.label} ${weight(weights[k.value])}`).join(" · ");
}

/** Months, for the median time to settle: "under a month", "1 month", "2.5 months". */
export function months(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value < 1) return "under a month";
  return value === 1 ? "1 month" : `${weight(value)} months`;
}
