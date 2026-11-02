/**
 * The Book traits page (issue #431): finding a trait of the catalogue to change for
 * the troupe, and what each change says, in a player's words.
 */
import type { CategoryOut, TraitOut } from "../../api/types";

/** How many traits a search lists at once; typing more narrows it. */
export const SHOWN = 40;

/**
 * The catalogue's book traits a troupe can change, in the catalogue's order: not a
 * troupe's own merits and flaws, nor what is worked out from the rest of the sheet.
 */
export function bookTraits(traits: TraitOut[], categories: CategoryOut[]): TraitOut[] {
  const order = new Map(categories.filter((c) => !c.derived).map((c, n) => [c.key, n]));
  return traits
    .filter((t) => !t.house && order.has(t.category))
    .sort((a, b) => order.get(a.category)! - order.get(b.category)! || a.name.localeCompare(b.name));
}

/**
 * The traits a search finds: every word in the name (or its description), in one
 * category or any. Those the troupe has changed come first, as most often looked for.
 */
export function findTraits(traits: TraitOut[], query: string, category: string): TraitOut[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const found = traits.filter(
    (t) =>
      (!category || t.category === category) &&
      words.every((w) => t.name.toLowerCase().includes(w) || (t.description ?? "").toLowerCase().includes(w)),
  );
  return [...found.filter((t) => t.changed), ...found.filter((t) => !t.changed)];
}

/** A trait's change, as the list of changes says it: "Banned: too swingy", "Own wording, added to the book's". */
export function changeSummary(change: { banned: boolean; ban_reason: string; wording?: string; wording_mode?: string }): string[] {
  const parts: string[] = [];
  if (change.banned) parts.push(change.ban_reason ? `Banned: ${change.ban_reason}` : "Banned");
  if (change.wording) parts.push(change.wording_mode === "replaces" ? "Own wording, in place of the book's" : "Own wording, added to the book's");
  return parts;
}
