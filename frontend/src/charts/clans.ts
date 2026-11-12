import { assignSlots } from "./categorical";
import type { ChartForm, Slot } from "./palette";

/**
 * The clan a chart groups a character under: a bloodline counts as its clan
 * ("Gangrel: Coyote" is Gangrel, as the rules name them), and a character with
 * no clan is "No clan".
 */
export function clanKey(clan: string | null | undefined): string {
  const name = (clan ?? "").split(":")[0]!.trim();
  return name || NO_CLAN;
}

export const NO_CLAN = "No clan";

/**
 * Stable clan colours for one troupe's charts (#706): the troupe's clans, most
 * characters first (then by name), take the categorical slots in order; past
 * the form's cap the rest share "Other". Pass the troupe's own counts, not one
 * chart's, and every chart of that troupe colours a clan the same, whatever it
 * filters. A clan joining or growing past another can move the colours, as it
 * changes which clans the troupe has most of.
 */
export function clanSlots(counts: readonly { clan: string | null | undefined; count: number }[], form: ChartForm = "adjacent"): Map<string, Slot> {
  const totals = new Map<string, number>();
  for (const { clan, count } of counts) {
    const key = clanKey(clan);
    totals.set(key, (totals.get(key) ?? 0) + count);
  }
  const order = [...totals].sort(([a, x], [b, y]) => y - x || a.localeCompare(b)).map(([key]) => key);
  return assignSlots(order, form);
}
