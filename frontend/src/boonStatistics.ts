import type { BoonStatisticsOut } from "./api/types";
import type { BoonKind } from "./boons";
import { KINDS } from "./boons";

/*
 * Boon statistics (#702): shaping the API's numbers for the statistics page's charts,
 * as plain functions so they can be tested without drawing anything. No d3 here.
 */

export type Statistics = BoonStatisticsOut;
export type MonthLine = Statistics["by_entered"][number];
export type StatNode = Statistics["nodes"][number];
export type StatLink = Statistics["links"][number];
export type Flow = Statistics["clan_flow"];
export type GameActivity = Statistics["games"][number];
export type Weights = Record<BoonKind, number>;

/** What the trends chart counts: boons registered or settled in each period, or those still open at its end. */
export type Measure = "registered" | "settled" | "open";
/** By the day each boon went in the ledger, or by the in-game night it was made (registering only). */
export type Basis = "entered" | "night";

/** Past this many months, the trends go by year. */
export const MONTHS_SHOWN = 60;

export type Period = { key: string; label: string };
export type Trend = { periods: Period[]; unit: "month" | "year"; byKind: Record<BoonKind, number[]>; totals: number[] };

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10" as "Oct 2026". */
export function monthLabel(month: string): string {
  return `${MONTH_NAMES[Number(month.slice(5, 7)) - 1]} ${month.slice(0, 4)}`;
}

/** Every month from the first to the last, "2025-11" to "2026-02", in order. */
export function monthsBetween(first: string, last: string): string[] {
  const found: string[] = [];
  let year = Number(first.slice(0, 4));
  let month = Number(first.slice(5, 7));
  const endYear = Number(last.slice(0, 4));
  const endMonth = Number(last.slice(5, 7));
  while (year < endYear || (year === endYear && month <= endMonth)) {
    found.push(`${year}-${String(month).padStart(2, "0")}`);
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return found;
}

/**
 * The trends chart's numbers: for each period (a month, or a year past five years),
 * each kind's count or weight of boons registered, settled, or open at the period's
 * end. Open at a year's end is its last month's.
 */
export function trend(lines: readonly MonthLine[], measure: Measure, weighted: boolean): Trend {
  const empty = (): Record<BoonKind, number[]> => Object.fromEntries(KINDS.map((k) => [k.value, []])) as unknown as Record<BoonKind, number[]>;
  if (lines.length === 0) return { periods: [], unit: "month", byKind: empty(), totals: [] };
  const sorted = [...new Set(lines.map((l) => l.month))].sort();
  const months = monthsBetween(sorted[0]!, sorted.at(-1)!);
  const unit = months.length > MONTHS_SHOWN ? "year" : "month";
  const periodOf = (month: string) => (unit === "year" ? month.slice(0, 4) : month);
  const keys = [...new Set(months.map(periodOf))];
  const at = new Map(keys.map((k, i) => [k, i]));
  const byKind = empty();
  for (const k of KINDS) byKind[k.value] = keys.map(() => 0);
  const value = (l: MonthLine) => {
    if (measure === "registered") return weighted ? l.registered_weight : l.registered;
    if (measure === "settled") return weighted ? l.settled_weight : l.settled;
    return weighted ? l.open_weight : l.open;
  };
  // Open is what stood at the end, so a year takes its last month's, not a sum.
  const lastMonth = new Map<string, string>();
  for (const m of months) lastMonth.set(periodOf(m), m);
  for (const l of lines) {
    const p = periodOf(l.month);
    if (measure === "open" && lastMonth.get(p) !== l.month) continue;
    byKind[l.kind][at.get(p)!] = round(byKind[l.kind][at.get(p)!]! + value(l));
  }
  const periods = keys.map((key) => ({ key, label: unit === "year" ? key : monthLabel(key) }));
  const totals = keys.map((_, i) => round(KINDS.reduce((n, k) => n + byKind[k.value][i]!, 0)));
  return { periods, unit, byKind, totals };
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}

/** What the network shows. */
export type NetworkFilter = {
  clan: string | null;
  sect: string | null;
  // Only boons with a title holder on one side.
  court: boolean;
  kinds: ReadonlySet<BoonKind>;
  // Hide links lighter than this.
  minWeight: number;
};

/** The heaviest a link's kinds make it, counting only the kinds shown. */
export function linkWeight(link: StatLink, kinds: ReadonlySet<BoonKind>, weights: Weights): number {
  return round(Object.entries(link.kinds).reduce((n, [kind, count]) => (kinds.has(kind as BoonKind) ? n + count * weights[kind as BoonKind] : n), 0));
}

/** The heaviest kind among a link's, for its colour. */
export function heaviestKind(link: StatLink, kinds: ReadonlySet<BoonKind>): BoonKind {
  let found: BoonKind = "trivial";
  for (const k of KINDS) if (kinds.has(k.value) && (link.kinds[k.value] ?? 0) > 0) found = k.value;
  return found;
}

/**
 * The lightest link to show so the network stays readable: none hidden while there
 * are at most `cap` links, else the weight that keeps about `cap` of the heaviest.
 */
export function readableMinimum(links: readonly StatLink[], cap = 120): number {
  if (links.length <= cap) return 0;
  const sorted = links.map((l) => l.weight).sort((a, b) => b - a);
  return sorted[cap - 1]!;
}

export type Network = { nodes: StatNode[]; links: (StatLink & { shown: number; kind: BoonKind })[] };

/** A party's clan as the charts group it: a bloodline counts as its clan. */
export function clanOf(node: StatNode): string {
  return (node.who.clan ?? "").split(":")[0]!.trim() || (node.who.character_id ? "Not known" : "Name only");
}

/**
 * The network as filtered: the links that pass, weighed by the kinds shown, and the
 * people at their ends. A clan, sect or the court keeps every link with someone of
 * it on either side.
 */
export function network(nodes: readonly StatNode[], links: readonly StatLink[], filter: NetworkFilter, weights: Weights): Network {
  const byKey = new Map(nodes.map((n) => [n.who.key, n]));
  const passes = (n: StatNode | undefined) =>
    !!n && (filter.clan === null || clanOf(n) === filter.clan) && (filter.sect === null || (n.who.sect ?? "") === filter.sect) && (!filter.court || n.who.titles.length > 0);
  const kept = links
    .map((l) => ({ ...l, shown: linkWeight(l, filter.kinds, weights), kind: heaviestKind(l, filter.kinds) }))
    .filter((l) => l.shown > 0 && l.shown >= filter.minWeight && (passes(byKey.get(l.debtor)) || passes(byKey.get(l.creditor))));
  const ends = new Set(kept.flatMap((l) => [l.debtor, l.creditor]));
  return { nodes: nodes.filter((n) => ends.has(n.who.key)), links: kept };
}

/** A node's radius: by everything on its boons, owed and owing, on a square-root scale. */
export function radius(node: StatNode, heaviest: number): number {
  const total = node.owes + node.owed;
  if (heaviest <= 0) return 4;
  return 4 + 14 * Math.sqrt(total / heaviest);
}

/**
 * The flow chart's matrix: the heaviest groups kept, the rest folded into "Other",
 * so the circle has at most `most` arcs.
 */
export function folded(flow: Flow, most = 8): Flow {
  if (flow.groups.length <= most) return flow;
  const keep = flow.groups.slice(0, most - 1);
  const at = (g: string) => (keep.includes(g) ? keep.indexOf(g) : keep.length);
  const groups = [...keep, "Other"];
  const matrix = groups.map(() => groups.map(() => 0));
  const counts = groups.map(() => groups.map(() => 0));
  flow.groups.forEach((a, i) =>
    flow.groups.forEach((b, j) => {
      matrix[at(a)]![at(b)] = round(matrix[at(a)]![at(b)]! + flow.matrix[i]![j]!);
      counts[at(a)]![at(b)]! += flow.counts[i]![j]!;
    }),
  );
  return { groups, matrix, counts };
}

/** Each pair of groups once, with what runs each way, heaviest first: the flow chart's table. */
export function flowPairs(flow: Flow): { from: string; to: string; owed: number; back: number; boons: number }[] {
  const found: { from: string; to: string; owed: number; back: number; boons: number }[] = [];
  flow.groups.forEach((a, i) =>
    flow.groups.forEach((b, j) => {
      if (j < i) return;
      const owed = flow.matrix[i]![j]!;
      const back = i === j ? 0 : flow.matrix[j]![i]!;
      const boons = flow.counts[i]![j]! + (i === j ? 0 : flow.counts[j]![i]!);
      if (owed + back > 0) found.push({ from: a, to: b, owed, back, boons });
    }),
  );
  return found.sort((x, y) => y.owed + y.back - (x.owed + x.back) || x.from.localeCompare(y.from));
}

/** The games, oldest first, as the timeline draws them. */
export function timeline(games: readonly GameActivity[]): GameActivity[] {
  return [...games].sort((a, b) => a.game.starts_at.localeCompare(b.game.starts_at));
}
