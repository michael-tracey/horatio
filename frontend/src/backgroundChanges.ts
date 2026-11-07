/**
 * Backgrounds raised or lowered for a while (backend: horatio.downtime_effects): Crafts
 * and Performance raise Resources and Fame by 1 for the month; overtaxed Resources are
 * 2 lower for six games or three months, whichever is later.
 */
import type { BackgroundNowOut } from "./api/types";
import type { Dates } from "./dates";
import { lastsText } from "./influenceEffects";

const SOURCES: Record<string, string> = { crafts: "Crafts", performance: "Performance", overtaxed: "overtaxed" };

function signed(n: number): string {
  return n < 0 ? `−${-n}` : `+${n}`;
}

/** "Resources 3 (+1 this month, Crafts)"; "Resources 1 (−2 overtaxed, until 7 Feb 2027, or 6 more games if that is later)". */
export function changedText(b: BackgroundNowOut, dates: Pick<Dates, "date">, now: Date = new Date()): string {
  const parts = b.changes.map((c) => {
    const source = SOURCES[c.source] ?? c.source;
    if (c.ends_at === null) return `${signed(c.delta)} this month, ${source}`;
    return `${signed(c.delta)} ${source}, ${lastsText({ ends_at: c.ends_at, games_left: c.games_left }, dates, now)}`;
  });
  return `${b.trait} ${b.now} (${parts.join("; ")})`;
}
