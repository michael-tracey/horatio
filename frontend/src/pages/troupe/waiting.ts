/**
 * What waits on a troupe's staff (issue #373), from GET /troupes/{id}/waiting: the
 * Waiting on you box, the counts on the troupe's tabs and the staff's home page all
 * read the same lines, so they never disagree.
 */
import type { WaitingLine } from "../../api/types";

/** The troupe tabs that show a count of what waits on them. */
export type WaitingTab = "approvals" | "characters" | "downtimes" | "work" | "quests" | "influence";

/**
 * The tab each kind of line counts on. The open cycle's line has no count, and
 * responses not yet written are everyone's writing, counted for each person on My
 * work instead, so neither counts on a tab.
 */
const TAB_OF: Record<string, WaitingTab> = {
  approvals: "approvals",
  backstories: "characters",
  status_to_resolve: "characters",
  cycle_late: "downtimes",
  cycle_unassigned: "downtimes",
  deliveries: "downtimes",
  shortfalls: "downtimes",
  my_responses: "work",
  quest_requests: "quests",
  influence_details: "influence",
  effects_ending: "influence",
};

/** How many wait on each tab. */
export function tabCounts(lines: WaitingLine[] | undefined): Record<WaitingTab, number> {
  const counts: Record<WaitingTab, number> = { approvals: 0, characters: 0, downtimes: 0, work: 0, quests: 0, influence: 0 };
  for (const line of lines ?? []) {
    const tab = TAB_OF[line.kind];
    if (tab && line.count) counts[tab] += line.count;
  }
  return counts;
}

/** Everything the tabs count, for one figure per troupe. */
export function waitingTotal(lines: WaitingLine[] | undefined): number {
  return Object.values(tabCounts(lines)).reduce((sum, n) => sum + n, 0);
}

/**
 * When something is due, from the calendar days between today and its day in the
 * viewer's zone, each as "2026-11-07": "due in 7 days", "due tomorrow", "due today",
 * "due yesterday" or "due 3 days ago".
 */
export function dueText(today: string, due: string): string {
  const days = Math.round((Date.parse(due) - Date.parse(today)) / 86_400_000);
  if (days > 1) return `due in ${days} days`;
  if (days === 1) return "due tomorrow";
  if (days === 0) return "due today";
  if (days === -1) return "due yesterday";
  return `due ${-days} days ago`;
}
