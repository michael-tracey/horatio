/** Retainers (core book p. 104): each bought on its own, with its own name and dots. */

import type { RetainerOut } from "../../api/types";

/** How a Retainer is named in lists: one held without a name, from before each was named, says so. */
export function retainerName(r: Pick<RetainerOut, "name">): string {
  return r.name || "A Retainer not yet named";
}

/** Where a Retainer's dots come from, when not from buying it on the sheet. */
export function retainerSource(r: Pick<RetainerOut, "bought" | "from_merit">): string | null {
  if (r.from_merit) return `from ${r.from_merit}`;
  if (!r.bought) return "listed before each Retainer was bought on its own";
  return null;
}

/** What the book says of a lost Retainer, for the note beside it. */
export const LOST_NOTE =
  "A lost Retainer's dots are out of reach for one game or two weeks, whichever is longer, for each dot, unless a replacement is found (p. 104). Staff decide when.";

export const LOST_WORDS: Record<string, string> = { released: "Released", killed: "Killed" };
