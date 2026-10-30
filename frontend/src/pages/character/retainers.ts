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
