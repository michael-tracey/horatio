import type { CostOut } from "../../api/types";

export type Scheme = CostOut["scheme"];

/** How a price is set: the scheme, with its amount or table. */
export type Pricing = { scheme: Scheme; rate: number | null; table: number[] | null };

/** The ways a storyteller can price something, in the order offered. */
export const SCHEMES: { value: Scheme; label: string }[] = [
  { value: "per_dot", label: "The same for each dot" },
  { value: "progressive", label: "Rising: each dot costs its number × the amount" },
  { value: "fixed", label: "One price, whatever the rating" },
  { value: "table", label: "A price for each dot in turn" },
  { value: "free", label: "Free" },
  { value: "not_allowed", label: "Cannot be bought" },
];

/**
 * The full price of `rating` dots, as the backend works it out
 * (horatio.rules.pricing.price): null when the price cannot be had.
 */
export function priceAt(pricing: Pricing, rating: number): number | null {
  if (rating === 0 || pricing.scheme === "free") return 0;
  if (pricing.scheme === "not_allowed") return null;
  if (pricing.scheme === "table") {
    const table = pricing.table ?? [];
    return rating > table.length ? null : table.slice(0, rating).reduce((a, b) => a + b, 0);
  }
  const rate = pricing.rate;
  if (rate === null) return null;
  if (pricing.scheme === "per_dot") return rate * rating;
  if (pricing.scheme === "progressive") return (rate * rating * (rating + 1)) / 2;
  return rate;
}

/** The ratings a preview shows: 1 to 5, or fewer where the category stops sooner. */
export function previewRatings(maxRating: number | null): number[] {
  return Array.from({ length: Math.min(5, maxRating ?? 5) }, (_, i) => i + 1);
}

/** Whether a scheme is the same at every rating, so a preview shows one price. */
export function flat(pricing: Pricing): boolean {
  return pricing.scheme === "fixed" || pricing.scheme === "free" || pricing.scheme === "not_allowed";
}

type Subject = Pick<CostOut, "category" | "trait" | "condition">;

/** How specific a price is: one naming a trait beats a whole category, then more conditions beat fewer. */
function specificity(cost: Subject): [number, number] {
  return [cost.trait ? 1 : 0, Object.keys(cost.condition ?? {}).length];
}

function compare(a: [number, number], b: [number, number]): number {
  return a[0] - b[0] || a[1] - b[1];
}

/** Whether two conditions could hold together: no fact tested both ways. */
function compatible(a: CostOut["condition"], b: CostOut["condition"]): boolean {
  return Object.entries(a ?? {}).every(([fact, test]) => !(fact in (b ?? {})) || JSON.stringify(test) === JSON.stringify(b?.[fact]));
}

/** Whether every test in `a` is also in `b`, so `a` holds wherever `b` does. */
function within(a: CostOut["condition"], b: CostOut["condition"]): boolean {
  return Object.entries(a ?? {}).every(([fact, test]) => fact in (b ?? {}) && JSON.stringify(test) === JSON.stringify(b?.[fact]));
}

/**
 * For a troupe price about to be set, the rule set's price it would replace
 * (the one that applies now to what the new price covers, as a troupe price
 * wins a tie) and those that would still apply because they are more specific.
 */
export function overlaps(subject: Subject, book: CostOut[]): { replaces: CostOut[]; stillApplies: CostOut[] } {
  const related = book.filter(
    (c) =>
      !c.house &&
      c.category === subject.category &&
      (c.trait === null || subject.trait === null || c.trait === subject.trait) &&
      compatible(c.condition, subject.condition),
  );
  const mine = specificity(subject);
  const covered = related.filter((c) => compare(specificity(c), mine) <= 0 && within(c.condition, subject.condition));
  const best = covered.reduce<[number, number] | null>((top, c) => (top && compare(top, specificity(c)) >= 0 ? top : specificity(c)), null);
  return {
    replaces: covered.filter((c) => best && compare(specificity(c), best) === 0),
    stillApplies: related.filter((c) => compare(specificity(c), mine) > 0),
  };
}

/** The table a storyteller typed, "1, 4, 6", as numbers; null if any part is not a whole number. */
export function parseTable(text: string): number[] | null {
  const parts = text.split(/[\s,]+/).filter(Boolean);
  if (parts.length === 0 || parts.some((p) => !/^-?\d+$/.test(p))) return null;
  return parts.map(Number);
}
