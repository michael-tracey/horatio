/** Retainers (core book p. 104): each bought on its own, with its own name and dots. */

import type { RetainerOut } from "../../api/types";

/**
 * How a Retainer is named in lists: one a merit gives, not named yet, by what it
 * is; one held without a name, from before each was named, says so.
 */
export function retainerName(r: Pick<RetainerOut, "name"> & Partial<Pick<RetainerOut, "kind">>): string {
  if (r.name) return r.name;
  return r.kind ? `${r.kind}, not yet named` : "A Retainer not yet named";
}

/** The merits whose Retainers are given by the rules, so not added by hand. */
export function givingMerits(retainers: Pick<RetainerOut, "given" | "from_merit">[]): string[] {
  return [...new Set(retainers.filter((r) => r.given).map((r) => r.from_merit))];
}

/** A row of the sheet a Retainer can be listed under. */
type Row = { category: string; name: string; detail: string };

/** A row of the Retainers background: one Retainer bought, by its name. */
export const isRetainersRow = (t: Row) => t.category === "backgrounds" && t.name === "Retainers";

/**
 * Which Retainers are listed under which row of the sheet, each edited there on its
 * own: one bought, under its own Retainers row (by name); one from a merit, under that
 * merit. Any other (listed before each was bought on its own, or from a merit no longer
 * held) goes under the Retainers row held without a name, from the same time, or the
 * first Retainers row, or else the first merit with one.
 */
export function placeRetainers<T extends Row, R extends Pick<RetainerOut, "bought" | "name" | "from_merit">>(rows: T[], retainers: R[]): Map<T, R[]> {
  const under = new Map<T, R[]>();
  const put = (row: T, r: R) => under.set(row, [...(under.get(row) ?? []), r]);
  const bought = rows.filter(isRetainersRow);
  const merits = rows.filter((t) => t.category === "merits");
  const taken = new Set<T>();
  const left: R[] = [];
  for (const r of retainers) {
    const row = r.bought ? bought.find((t) => t.detail === r.name && !taken.has(t)) : r.from_merit ? merits.find((t) => t.name === r.from_merit) : undefined;
    if (!row) {
      left.push(r);
      continue;
    }
    if (r.bought) taken.add(row);
    put(row, r);
  }
  const home = bought.find((t) => !t.detail) ?? bought[0] ?? merits.find((t) => under.has(t));
  if (home) for (const r of left) put(home, r);
  return under;
}

/** What a row's Retainers are called on the sheet: "Retainer: Bocephus", "Retainers from Ardent Companion". */
export function sectionLabel(t: Row): string {
  if (!isRetainersRow(t)) return `Retainers from ${t.name}`;
  return t.detail ? `Retainer: ${t.detail}` : "Retainer not yet named";
}

/** Whether a merit speaks of Retainers, so one can be added by hand under it (Master of the Hounds' second hound). */
export function addsRetainers(description: string | null | undefined): boolean {
  return /\bretainers?\b/i.test(description ?? "");
}

/** Where a Retainer's dots come from, when not from buying it on the sheet. */
export function retainerSource(r: Pick<RetainerOut, "bought" | "from_merit">): string | null {
  if (r.from_merit) return `from ${r.from_merit}`;
  if (!r.bought) return "listed before each Retainer was bought on its own";
  return null;
}

/** What the book says of a lost Retainer, for the note beside it. */
export const LOST_NOTE =
  "A lost Retainer's dots are out of reach for one game or two weeks for each dot, whichever is longer, while a replacement is found (p. 104). The games are the home troupe's, as its profile schedules them.";

/** When a lost Retainer's dots come back, in words; null for one not lost, or lost on no day. */
export function backText(
  r: Pick<RetainerOut, "lost" | "back_from" | "back_games" | "back_on" | "away">,
  date: (iso: string) => string,
): string | null {
  if (!r.lost) return null;
  if (r.back_on) return r.away ? `Its dots come back on ${date(r.back_on)}.` : `Its dots came back on ${date(r.back_on)}.`;
  if (!r.back_from) return null;
  const games = r.back_games === 1 ? "1 game has" : `${r.back_games} games have`;
  return `Its dots come back once ${games} gone by since, and not before ${date(r.back_from)}.`;
}

export const LOST_WORDS: Record<string, string> = { released: "Released", killed: "Killed" };

/** A Retainer's neglect, under the house rule of upkeep (#442): null while it is not neglected. */
export function neglectText(r: Pick<RetainerOut, "neglected_on">, date: (iso: string) => string): string | null {
  return r.neglected_on ? `Neglected since ${date(r.neglected_on)}: its upkeep went unpaid.` : null;
}

/** The XP its growth gave (#442): banked here, and what its NPC has to spend; null for none. */
export function growthText(r: Pick<RetainerOut, "banked_xp" | "npc_xp" | "npc_name">): string | null {
  const parts: string[] = [];
  if (r.banked_xp) parts.push(`${r.banked_xp} XP banked`);
  if (r.npc_xp != null) parts.push(`${r.npc_name ?? "Its NPC"} has ${r.npc_xp} XP to spend`);
  return parts.length ? parts.join(" · ") : null;
}
