/** Running a downtime cycle: chasing submissions, and the lines in the lists of cycles. */

const DAY = 86_400_000;

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Where a participant's downtime stands. */
export type Standing = "submitted" | "started" | "not started" | "removed";

/** A standing as a badge says it. */
export const STANDING_NAMES: Record<Standing, string> = { submitted: "Submitted", started: "Started", "not started": "Not started", removed: "Removed" };

const CYCLE_STATUS: Record<string, string> = { draft: "Draft", open: "Open", closed: "Closed", complete: "Complete" };

/** A cycle's status as a badge says it: "Open". */
export function cycleStatus(status: string): string {
  return CYCLE_STATUS[status] ?? status;
}

export function standing(p: { removed: boolean; submission_status?: string | null }): Standing {
  if (p.removed) return "removed";
  if (p.submission_status === "submitted") return "submitted";
  return p.submission_status ? "started" : "not started";
}

type Chased = { removed: boolean; submission_status?: string | null; player_id: string; character_name: string };

/** "12 submitted · 5 started · 13 not started", leaving out what there is none of. */
export function chaseSummary(participants: Chased[]): string {
  const count = (s: Standing) => participants.filter((p) => standing(p) === s).length;
  const parts = (["submitted", "started", "not started", "removed"] as const).map((s) => [count(s), s] as const).filter(([n]) => n > 0);
  return parts.map(([n, s]) => `${n} ${s}`).join(" · ") || "No one is taking part.";
}

/** Those taking part whose downtimes aren't submitted. */
export function notSubmitted<T extends Chased>(participants: T[]): T[] {
  return participants.filter((p) => !p.removed && p.submission_status !== "submitted");
}

/** How many players a reminder reaches: one each, however many of their characters are waiting. */
export function playersToRemind(participants: Chased[]): number {
  return new Set(notSubmitted(participants).map((p) => p.player_id)).size;
}

/** "Agnes, Bram and Corin", or "Agnes, Bram, Corin and 4 others" past `most`. */
export function nameList(names: string[], most = 5): string {
  const shown = names.length > most ? [...names.slice(0, most - 1), plural(names.length - most + 1, "other", "others")] : names;
  if (shown.length <= 1) return shown.join("");
  return `${shown.slice(0, -1).join(", ")} and ${shown.at(-1)}`;
}

/**
 * How long is left to submit: "7 days left · grace to Mon 9 Nov", then once it
 * is due, "Overdue · late downtimes taken until Mon 9 Nov", then "The grace period is over".
 */
export function timeLeft(closesAt: string, graceEndsAt: string, dueDay: (at: string) => string, now: Date = new Date()): string {
  const toClose = new Date(closesAt).getTime() - now.getTime();
  const toGrace = new Date(graceEndsAt).getTime() - now.getTime();
  const grace = toGrace > toClose;
  if (toClose > 0) {
    const days = Math.floor(toClose / DAY);
    const left = days === 0 ? "Less than a day left" : `${plural(days, "day", "days")} left`;
    return grace ? `${left} · grace to ${dueDay(graceEndsAt)}` : left;
  }
  if (toGrace > 0) return `Overdue · late downtimes taken until ${dueDay(graceEndsAt)}`;
  return "The grace period is over";
}

type Summary = { status: string; closes_at: string; participants: number; submitted: number; responses: number; written: number };

/** A cycle's line in the troupe's list: "Due Sat 7 Nov · 3 of 8 submitted", or once closed, "8 submitted · 5 of 20 responses written". */
export function cycleLine(c: Summary, dueDay: (at: string) => string): string {
  if (c.status === "draft") return `Due ${dueDay(c.closes_at)} · not open yet`;
  if (c.status === "open") return `Due ${dueDay(c.closes_at)} · ${c.submitted} of ${c.participants} submitted`;
  return `${c.submitted} submitted · ${c.written} of ${plural(c.responses, "response", "responses")} written`;
}

/** A cycle's line in My work: "3 for you to write · 2 open to narrators". */
export function workLine(c: { to_write?: number; open_to_narrators?: number }): string {
  const parts = [
    ...(c.to_write ? [`${c.to_write} for you to write`] : []),
    ...(c.open_to_narrators ? [`${c.open_to_narrators} open to narrators`] : []),
  ];
  return parts.join(" · ") || "Nothing for you to write";
}
