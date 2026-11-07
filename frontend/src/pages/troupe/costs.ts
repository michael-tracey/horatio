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

/** What a price's condition can test (horatio.rules.splats): the Generation background, in-clan, and the clan. */
export type Fact = "generation" | "in_clan" | "clan" | "clan_family";
/** Is, at most or at least: at most and at least are for the Generation background only. */
export type Test = "eq" | "lte" | "gte";
/** One line of a condition: a fact, a test and a value, kept as the form's text ("2", "true", "Brujah"). */
export type Line = { fact: Fact; test: Test; value: string };
export type Condition = Record<string, unknown>;

export const FACTS: { value: Fact; label: string }[] = [
  { value: "generation", label: "Generation background" },
  { value: "in_clan", label: "In-clan" },
  { value: "clan", label: "Clan or bloodline" },
  { value: "clan_family", label: "Clan and its bloodlines" },
];

export const TESTS: { value: Test; label: string }[] = [
  { value: "eq", label: "is" },
  { value: "lte", label: "at most" },
  { value: "gte", label: "at least" },
];

/** A new line for a fact, with a value to start from. */
export function newLine(fact: Fact): Line {
  return { fact, test: "eq", value: fact === "generation" ? "1" : fact === "in_clan" ? "true" : "" };
}

/**
 * The lines as a condition the server takes, or why they cannot be one yet. One
 * Generation line of "is" is a bare value, as the book writes it; more make a range.
 */
export function toCondition(lines: Line[]): { condition: Condition | null } | { problem: string } {
  const condition: Condition = {};
  const generation: Record<string, number> = {};
  for (const line of lines) {
    const label = FACTS.find((f) => f.value === line.fact)?.label ?? line.fact;
    if (line.fact === "generation") {
      if (line.test in generation) return { problem: `${label} is “${TESTS.find((t) => t.value === line.test)?.label}” twice.` };
      generation[line.test] = Number(line.value);
      continue;
    }
    if (line.fact in condition) return { problem: `${label} is there twice.` };
    if (!line.value) return { problem: `Choose the ${label.toLowerCase()}.` };
    condition[line.fact] = line.fact === "in_clan" ? line.value === "true" : line.value;
  }
  const tests = Object.keys(generation);
  if (tests.length === 1 && tests[0] === "eq") condition.generation = generation.eq;
  else if (tests.length) condition.generation = generation;
  return { condition: Object.keys(condition).length ? condition : null };
}

/**
 * A condition as lines, to change it; null where the lines cannot say it (a test of
 * "not", or of one of several). The book's "below 3" reads as "at most 2".
 */
export function linesOf(condition: Condition | null | undefined): Line[] | null {
  const lines: Line[] = [];
  for (const [fact, test] of Object.entries(condition ?? {})) {
    if (fact === "generation") {
      const tests = typeof test === "number" ? { eq: test } : test;
      if (typeof tests !== "object" || tests === null) return null;
      for (const [op, value] of Object.entries(tests)) {
        if (typeof value !== "number") return null;
        if (op === "eq" || op === "lte" || op === "gte") lines.push({ fact, test: op, value: String(value) });
        else if (op === "lt") lines.push({ fact, test: "lte", value: String(value - 1) });
        else if (op === "gt") lines.push({ fact, test: "gte", value: String(value + 1) });
        else return null;
      }
    } else if (fact === "in_clan" && typeof test === "boolean") lines.push({ fact, test: "eq", value: String(test) });
    else if ((fact === "clan" || fact === "clan_family") && typeof test === "string") lines.push({ fact, test: "eq", value: test });
    else return null;
  }
  return lines;
}

/** Whether two conditions are the same, whatever order their facts are in. */
export function sameCondition(a: Condition | null | undefined, b: Condition | null | undefined): boolean {
  const sorted = (value: unknown): unknown =>
    value && typeof value === "object" && !Array.isArray(value)
      ? Object.entries(value)
          .sort(([x], [y]) => x.localeCompare(y))
          .map(([k, v]) => [k, sorted(v)])
      : value;
  return JSON.stringify(sorted(a ?? {})) === JSON.stringify(sorted(b ?? {}));
}
