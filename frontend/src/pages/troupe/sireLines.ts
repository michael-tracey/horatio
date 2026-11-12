import type { SireLineNodeOut } from "../../api/types";

/**
 * A troupe's sire lines (#707) as the tree draws them: one hidden root above every
 * eldest known, so the forest lays out as one tree. A collapsed character keeps its
 * childer out of the drawing and says how many are under it.
 */
export type SireTree = {
  node: SireLineNodeOut | null;
  children: SireTree[];
  // How many are folded away under it, however far down, while it is collapsed.
  folded: number;
};

/** How a retired character left, as the tree says it. */
export const LEFT: Record<string, string> = {
  final_death: "Final Death",
  off_field: "Off-field",
  inactive: "Inactive",
};

const byName = (a: SireLineNodeOut, b: SireLineNodeOut) => a.name.localeCompare(b.name) || a.key.localeCompare(b.key);

/**
 * The forest as one tree. A node whose sire isn't there is a root. Without `lone`,
 * a character with no known sire and no childer is left out: it has no line to draw.
 */
export function sireTree(nodes: readonly SireLineNodeOut[], { collapsed = new Set<string>(), lone = false }: { collapsed?: ReadonlySet<string>; lone?: boolean } = {}): SireTree {
  const known = new Set(nodes.map((n) => n.key));
  const childer = new Map<string, SireLineNodeOut[]>();
  for (const n of nodes) {
    if (n.sire_key && known.has(n.sire_key)) childer.set(n.sire_key, [...(childer.get(n.sire_key) ?? []), n]);
  }
  const under = (key: string): number => (childer.get(key) ?? []).reduce((sum, c) => sum + 1 + under(c.key), 0);
  const grow = (n: SireLineNodeOut): SireTree => {
    if (collapsed.has(n.key)) return { node: n, children: [], folded: under(n.key) };
    return { node: n, children: [...(childer.get(n.key) ?? [])].sort(byName).map(grow), folded: 0 };
  };
  const roots = nodes.filter((n) => !n.sire_key || !known.has(n.sire_key)).filter((n) => lone || childer.has(n.key));
  return { node: null, children: [...roots].sort(byName).map(grow), folded: 0 };
}

/** How many characters stand alone, with no known sire and no childer. */
export function loneCount(nodes: readonly SireLineNodeOut[]): number {
  const known = new Set(nodes.map((n) => n.key));
  const sires = new Set(nodes.map((n) => n.sire_key).filter((k): k is string => !!k && known.has(k)));
  return nodes.filter((n) => (!n.sire_key || !known.has(n.sire_key)) && !sires.has(n.key)).length;
}

/** What a node is, under its name: its clan, generation, and how it left. */
export function about(n: SireLineNodeOut): string[] {
  const parts: string[] = [];
  if (n.clan) parts.push(n.clan);
  if (n.generation) parts.push(`${ordinal(n.generation)} generation`);
  if (n.kind === "named") parts.push("known by name only");
  if (n.kind === "elsewhere") parts.push("outside the troupe");
  if (n.kind === "npc") parts.push("NPC");
  if (n.retired) parts.push(left(n));
  return parts;
}

/** How a retired character left: "Final Death", or "retired" where no reason was kept. */
export function left(n: Pick<SireLineNodeOut, "left_reason">): string {
  return (n.left_reason && LEFT[n.left_reason]) || "retired";
}

/** 1st, 2nd, 3rd, 4th… 11th, 12th, 13th. */
export function ordinal(n: number): string {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

/** The lines as a table: each character with its sire, for screen readers and the table view. */
export function sireRows(nodes: readonly SireLineNodeOut[]): { name: string; sire: string; about: string }[] {
  const byKey = new Map(nodes.map((n) => [n.key, n]));
  return [...nodes].sort(byName).map((n) => ({
    name: n.name,
    sire: (n.sire_key && byKey.get(n.sire_key)?.name) || "—",
    about: about(n).join(", "),
  }));
}
