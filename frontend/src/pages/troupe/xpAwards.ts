/** The bulk award screen's sums (issue #55), apart from the screen so they can be tested. */

export type Amounts = Record<string, number>;

/** Everyone at the set amount. */
export function everyone(ids: string[], amount: number): Amounts {
  return Object.fromEntries(ids.map((id) => [id, amount]));
}

/** One character's amount moved by `by`, never below 0. */
export function nudge(amounts: Amounts, id: string, by: number): Amounts {
  return { ...amounts, [id]: Math.max(0, (amounts[id] ?? 0) + by) };
}

/** Who gets something, and how much in all. */
export function totals(amounts: Amounts): { characters: number; total: number } {
  const given = Object.values(amounts).filter((n) => n > 0);
  return { characters: given.length, total: given.reduce((a, b) => a + b, 0) };
}
