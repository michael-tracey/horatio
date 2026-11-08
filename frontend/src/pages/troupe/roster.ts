/**
 * The troupe Characters list's table, kept apart from the screen so it can be
 * tested: what its Clan cell says, and the order its headings sort it in.
 */

/** The social ages, youngest first: the order Age sorts in. */
export const AGES = ["Neonate", "Ancilla", "Elder"];

/** The Clan cell: the clan, "No clan yet" for a vampire without one, and nothing
 * for what is no vampire, whose age says what it is instead (Mortal, Ghoul). */
export function clanText(clan: string | null, socialAge: string): string | null {
  return clan ?? (AGES.includes(socialAge) ? "No clan yet" : null);
}

/** Where Age puts a character: Neonate, Ancilla, Elder, then anything else (Ghoul,
 * Mortal) by name after them. */
export function ageRank(age: string): string {
  const at = AGES.indexOf(age);
  return at < 0 ? `9 ${age}` : String(at);
}

/** A heading the list is sorted by, and which way; null for the list's own order,
 * home characters first. */
export type Sort = { by: string; descending: boolean } | null;

/** Pressing a heading sorts by it, A to Z (or lowest first); again, Z to A; a third
 * time, back to the list's own order. */
export function nextSort(sort: Sort, by: string): Sort {
  if (sort?.by !== by) return { by, descending: false };
  return sort.descending ? null : { by, descending: true };
}

/** The rows in the order `key` gives them, keeping the list's order among equals.
 * A row with nothing to sort by (no player, no clan) goes last either way. */
export function sortRows<T>(rows: T[], key: ((row: T) => string | number | null) | null, descending: boolean): T[] {
  if (!key) return rows;
  const keyed = rows.map((row, at) => ({ row, at, value: key(row) }));
  keyed.sort((a, b) => {
    if (a.value === null || b.value === null) return a.value === b.value ? a.at - b.at : a.value === null ? 1 : -1;
    const order = typeof a.value === "number" && typeof b.value === "number" ? a.value - b.value : String(a.value).localeCompare(String(b.value));
    return (descending ? -order : order) || a.at - b.at;
  });
  return keyed.map((k) => k.row);
}

/** Which characters the list shows: player characters (the default), NPCs, or
 * everyone. Kept in the address as `?show=npcs` or `?show=everyone`. */
export type Show = "pcs" | "npcs" | "everyone";

/** The choice the address holds; anything else is player characters. */
export function showOf(param: string | null): Show {
  return param === "npcs" || param === "everyone" ? param : "pcs";
}

/** Whether the choice shows a character of this kind (pc or npc). */
export function shows(show: Show, kind: string): boolean {
  return show === "everyone" || (show === "npcs") === (kind === "npc");
}
