/**
 * The Troupes page's list (issue #366): what each row says to choose a troupe
 * by, which come first, and the search a long list gets.
 */
import type { TroupeOut } from "../api/types";

/** Past this many troupes, the list gets a search box. */
export const SEARCH_FROM = 8;

/** How long a description's excerpt runs, in characters. */
const EXCERPT = 160;

/**
 * The start of a description as one line of plain text: its first paragraph,
 * without Markdown's heading, list and emphasis marks, cut at a word near
 * `EXCERPT` characters.
 */
export function excerpt(description: string): string {
  const first = description.trim().split(/\n\s*\n/)[0] ?? "";
  const plain = first
    .split("\n")
    .map((line) => line.replace(/^\s*(#{1,6}\s+|[-*+]\s+|>\s*)/, ""))
    .join(" ")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_`]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (plain.length <= EXCERPT) return plain;
  const cut = plain.slice(0, EXCERPT);
  const space = cut.lastIndexOf(" ");
  return `${(space > EXCERPT / 2 ? cut.slice(0, space) : cut).replace(/[\s,;:.]+$/, "")}…`;
}

/** The troupes the person plays in or runs, first; then the rest, each by name. */
export function ownFirst(troupes: TroupeOut[]): TroupeOut[] {
  const own = (t: TroupeOut) => (t.my_characters.length > 0 || t.my_role ? 0 : 1);
  return [...troupes].sort((a, b) => own(a) - own(b) || a.name.localeCompare(b.name));
}

/** Whether a troupe's name, place or description holds every word searched for. */
export function matches(troupe: TroupeOut, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const text = `${troupe.name} ${troupe.place} ${troupe.description}`.toLowerCase();
  return words.every((w) => text.includes(w));
}
