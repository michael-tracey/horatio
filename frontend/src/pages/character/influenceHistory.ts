/** A character's influence history (issue #135; backend: horatio.influence_history). */
import type { HistoryEntryOut, InfluenceHistoryOut } from "../../api/types";
import type { Dates } from "../../dates";
import { TYPE_NAMES, type InfluenceType } from "../../influence";
import { nextDay } from "../troupe/influenceLog";

export type HistoryFilters = {
  type: "" | InfluenceType;
  specialization: string;
  /** Days, "2026-07-11", from and to (both included), in the reader's zone. */
  from: string;
  to: string;
  /** Only what a Gossip or Word on the Street could still turn up. */
  findable: boolean;
};

export const NO_HISTORY_FILTERS: HistoryFilters = { type: "", specialization: "", from: "", to: "", findable: false };

/** The entries that pass the filters, still newest first. */
export function filterHistory(entries: HistoryEntryOut[], filters: HistoryFilters, dates: Dates): HistoryEntryOut[] {
  const since = filters.from ? dates.fromInput(`${filters.from}T00:00`).getTime() : -Infinity;
  const until = filters.to ? dates.fromInput(`${nextDay(filters.to)}T00:00`).getTime() : Infinity;
  return entries.filter((e) => {
    const at = new Date(e.happened_at).getTime();
    return (
      (!filters.type || e.type === filters.type) &&
      (!filters.specialization || e.specialization === filters.specialization) &&
      at >= since &&
      at < until &&
      (!filters.findable || e.findable)
    );
  });
}

/** Only ever the character's own blocks: "you blocked it twice". */
export function blocksText(blocks: number): string | null {
  if (blocks <= 0) return null;
  return `you blocked it ${blocks === 1 ? "once" : blocks === 2 ? "twice" : `${blocks} times`}`;
}

/** Where it came from, as the character's player reads it. */
export function historySource(entry: Pick<HistoryEntryOut, "source" | "cycle_name" | "game_number">): string {
  switch (entry.source) {
    case "downtime":
      return entry.cycle_name ? `Downtime: ${entry.cycle_name}` : "Downtime";
    case "game":
      return entry.game_number ? `At a game (game ${entry.game_number})` : "At a game";
    case "import":
      return "From the old influence log";
    case "quest":
      return entry.cycle_name ? `For a quest, in ${entry.cycle_name}` : "For a quest";
    default:
      return entry.cycle_name ? `Logged by staff, for ${entry.cycle_name}` : "Logged by staff";
  }
}

export type MonthLine = {
  type: InfluenceType;
  name: string;
  rating: number;
  spent: number;
  atGames: number;
  inDowntimes: number;
  byStaff: number;
  owed: number;
};

/**
 * This month's actions of each type, in the reader's calendar: how many are
 * spent, where, and how many are owed to the next cycle. Each dot of influence
 * is one action a month (MET: VtM core, p. 510). Types the character has no
 * rating in and has not used are left out.
 */
export function thisMonth(history: Pick<InfluenceHistoryOut, "entries" | "standings" | "owed">, dates: Dates, now: Date = new Date()): MonthLine[] {
  const month = dates.month(now);
  const recent = history.entries.filter((e) => dates.month(e.happened_at) === month);
  return history.standings
    .map((standing) => {
      const type = standing.type;
      const mine = recent.filter((e) => e.type === type);
      const count = (source: (s: HistoryEntryOut["source"]) => boolean) => mine.filter((e) => source(e.source)).reduce((n, e) => n + e.times, 0);
      const atGames = count((s) => s === "game");
      const inDowntimes = count((s) => s === "downtime");
      const byStaff = count((s) => s === "hand" || s === "import" || s === "quest");
      return {
        type,
        name: TYPE_NAMES[type],
        rating: standing.rating,
        spent: atGames + inDowntimes + byStaff,
        atGames,
        inDowntimes,
        byStaff,
        owed: history.owed.find((o) => o.type === type)?.amount ?? 0,
      };
    })
    .filter((line) => line.rating > 0 || line.spent > 0 || line.owed > 0);
}

/** "2 of 3 spent: 1 at a game, 1 in a downtime. 1 owed to the next cycle." An NPC with no rating: "2 spent". */
export function monthText(line: MonthLine): string {
  const where = [
    line.atGames && `${line.atGames} at ${line.atGames === 1 ? "a game" : "games"}`,
    line.inDowntimes && `${line.inDowntimes} in ${line.inDowntimes === 1 ? "a downtime" : "downtimes"}`,
    line.byStaff && `${line.byStaff} logged by staff`,
  ].filter(Boolean);
  let text = line.rating ? `${line.spent} of ${line.rating} spent` : `${line.spent} spent`;
  if (where.length) text += `: ${where.join(", ")}`;
  text += ".";
  if (line.owed) text += ` ${line.owed} owed to the next cycle.`;
  return text;
}
