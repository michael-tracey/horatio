import type { ExpiryIn, ExpiryOut } from "../../api/types";
import type { Dates } from "../../dates";

/** When an item expires, as its holder reads it (#443): "Expires after 2 more games", "Expires at the end of 30 Nov 2026". */
export function expiryText(expiry: ExpiryOut, dates: Dates, now: Date = new Date()): string {
  if (expiry.kind === "date" && expiry.on) return `Expires at the end of ${dates.day(expiry.on)}`;
  if (expiry.kind === "games") {
    const left = expiry.games_left ?? 0;
    if (left <= 0) return "Expires now";
    return `Expires after ${left} more ${left === 1 ? "game" : "games"}`;
  }
  const due = expiry.cycle_closes_at ? ` (due ${dates.dueDay(expiry.cycle_closes_at, now)})` : "";
  return `Expires when the downtime cycle ${expiry.cycle_name ?? ""} closes${due}`;
}

/** An expiry as the item editor holds it: "never", or one of the three kinds. */
export type ExpiryDraft = { kind: "never" | ExpiryIn["kind"]; on: string; games: string; note: string };

export const NO_EXPIRY: ExpiryDraft = { kind: "never", on: "", games: "1", note: "" };

/** An item's expiry, to change it: games as those left now. */
export function fromExpiry(expiry: ExpiryOut | null | undefined): ExpiryDraft {
  if (!expiry) return NO_EXPIRY;
  return { kind: expiry.kind, on: expiry.on ?? "", games: String(expiry.games_left ?? 1), note: expiry.note };
}

/** What the API takes: null for never. */
export function expiryBody(draft: ExpiryDraft): ExpiryIn | null {
  if (draft.kind === "never") return null;
  const note = draft.note.trim();
  if (draft.kind === "date") return { kind: "date", on: draft.on || null, note };
  if (draft.kind === "games") return { kind: "games", games: Number(draft.games) || null, note };
  return { kind: "cycle", note };
}
