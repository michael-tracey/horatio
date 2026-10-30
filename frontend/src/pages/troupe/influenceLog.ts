/** The influence log page's words and filters (backend: horatio.influence_log). */
import type { InfluenceEntryOut } from "../../api/types";
import type { Dates } from "../../dates";

export type LogFilters = {
  type: "" | "elite" | "underworld";
  specialization: string;
  /** "c:<character id>" for a character, "n:<name>" for someone not in Horatio. */
  who: string;
  action: string;
  /** Days, "2026-07-11", from and to (both included). */
  from: string;
  to: string;
  /** Only entries still waiting for their details. */
  needsDetails: boolean;
};

export const NO_FILTERS: LogFilters = { type: "", specialization: "", who: "", action: "", from: "", to: "", needsDetails: false };

/** The day after "2026-07-11": "2026-07-12". */
export function nextDay(day: string): string {
  const [y = 0, m = 1, d = 1] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
}

/** The log's query for these filters, with days counted in the reader's zone. */
export function logQuery(filters: LogFilters, dates: Dates) {
  const who = filters.who;
  return {
    type: filters.type || undefined,
    specialization: filters.specialization || undefined,
    character_id: who.startsWith("c:") ? who.slice(2) : undefined,
    name: who.startsWith("n:") ? who.slice(2) : undefined,
    action: filters.action || undefined,
    since: filters.from ? dates.fromInput(`${filters.from}T00:00`).toISOString() : undefined,
    until: filters.to ? dates.fromInput(`${nextDay(filters.to)}T00:00`).toISOString() : undefined,
    needs_details: filters.needsDetails || undefined,
  };
}

/** Who took it: the name it was logged under, its name now if changed, and whether it has left. */
export function whoText(entry: Pick<InfluenceEntryOut, "name" | "current_name" | "left_troupe">): string {
  let text = entry.name;
  if (entry.current_name) text += ` (now ${entry.current_name})`;
  if (entry.left_troupe) text += " (left the troupe)";
  return text;
}

/** Where it came from. */
export function sourceText(entry: Pick<InfluenceEntryOut, "source" | "cycle_name" | "reference">): string {
  switch (entry.source) {
    case "downtime":
      return entry.cycle_name ? `Downtime: ${entry.cycle_name}` : "Downtime";
    case "game":
      return "At a game";
    case "import":
      return entry.reference ? `Imported (${entry.reference})` : "Imported";
    case "quest":
      return entry.cycle_name ? `For a quest, for ${entry.cycle_name}` : "For a quest";
    default:
      return entry.cycle_name ? `By hand, for ${entry.cycle_name}` : "By hand";
  }
}
